#!/usr/bin/python3.9
import os
import json
import logging
import re
import requests
from logging import handlers
import schedule
import configparser
# 创建一个配置解析器对象
config = configparser.ConfigParser()

# 读取配置文件

exe_dir = os.getcwd() # exe可执行文件所在位置
path = os.path.join(exe_dir, "config.ini") # 拼接上配置文件，形成全路径
config.read(path)

# 读取配置项的值
Settings_network = config['Settings']['network']
Settings_domain = config['Settings']['domain']
Settings_subdomain = config['Settings']['subdomain']
Settings_ipfile = config['Settings']['ipfile']
Settings_ZoneId = config['Settings']['ZoneId']
Settings_DnsToken = config['Settings']['DnsToken']

from datetime import datetime
# 创建 'LOG' 目录，位于当前脚本所在目录
log_directory = os.path.join(os.getcwd(), "LOG")
os.makedirs(log_directory, exist_ok=True)

# 更新 Logger 类中的日志目录路径
class Logger(object):
    level_relations = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'crit': logging.CRITICAL
    }

    def __init__(self, log_dir=None, level='info', fmt='%(asctime)s - %(message)s'):
        if log_dir is None:
            log_dir = os.path.join(log_directory, datetime.now().strftime('%Y-%m-%d'))
        self.logger = logging.getLogger()
        format_str = logging.Formatter(fmt)
        self.logger.setLevel(self.level_relations.get(level))

        sh = logging.StreamHandler()
        sh.setFormatter(format_str)

        log_filename = f"{log_dir}/{datetime.now().strftime('%Y-%m-%d')}.log"
        th = logging.handlers.TimedRotatingFileHandler(
            filename=log_filename, when='D', interval=1, backupCount=3, encoding='utf-8'
        )
        th.setFormatter(format_str)

        self.logger.addHandler(sh)
        self.logger.addHandler(th)
        

# 查询子域名有没有创建DNS解析，返回id和ip，如果为空，返回-1
def Rget(ZoneName, ZoneId, Header):
    global id, ClientIp, ip
    url = 'https://api.cloudflare.com/client/v4/zones/' + ZoneId + '/dns_records'
    # 用于get查询的body数据，content配置127.0.0.1
    body = {
        'match': 'any',
        'type': 'A',
        'content': Settings_network,
        'name': ZoneName,
        'order': 'type',
        'page': '1',
        'per_page': '5',
        'proxied': False,
        'direction': 'desc'
    }
    # cloudflare请求方式get
    response = requests.get(url, headers=Header, params=body)
    # 转成dict进行查找处理
    Text = json.loads(response.text)
    domains = Text['result']
    #log.logger.info('DNS记录查询结果：' + str(domains))
    # 查找子域名在dict的第几个位置，取出id和IP地址，用来update DNS记录
    for num in range(len(domains)):
        domain = domains[num]['name']
        if domain == RecordName:
            id = domains[num]['id']
            ip = domains[num]['content']
            break
        else:
            id = -1
            ip = -1
    return (id, ip)

# 更新DNS记录
def Rupdate(ZoneId, RecordName, id, ip, Header):
    url = 'https://api.cloudflare.com/client/v4/zones/' + ZoneId + '/dns_records/' + id
    #Header = json.loads(Header)
    # 使用get查询到的数据，拼接body
    body = {
        'type': 'A',
        'name': str(RecordName),
        'content': ip,
        'ttl': 1,
        'proxied': False
    }
    body = json.dumps(body)
    # cloudflare请求方式put
    response = requests.put(url, headers=Header, data=body)
    # 转成dict进行查找处理
    Text = json.loads(response.text)
    domains = Text['result']    
    #log.logger.info('DNS记录修改结果：' + str(domains))
    # 在返回的dict查找子域名，确认是否更新成功
    domain = domains['name']
    if domain == RecordName:
        id = domains['id']
        ip = domains['content']
        log.logger.info('新的DNS记录更新成功，当前ID：' + str(id))
        log.logger.info('新的DNS记录更新成功，当前IP：' + str(ip))
        return (id, ip)
    else:
        log.logger.info('新的DNS记录更新失败')

# 创建DNS记录
def Rcreate(ZoneId, RecordName, ip, Header):
    global id
    url = 'https://api.cloudflare.com/client/v4/zones/' + ZoneId + '/dns_records'
    # 使用get查询到的数据，拼接body
    body = {
        'type': 'A',
        'name': str(RecordName),
        'content': ip,
        'ttl': 1,
        'priority': 10,
        'proxied': False
    }
    body = json.dumps(body)
    # cloudflare请求方式post
    response = requests.post(url, headers=Header, data=body)
    # 转成dict进行查找处理
    Text = json.loads(response.text)
    domains = Text['result']
    #log.logger.info('创建新DNS纪录结果：' + str(domains))
    # 在返回的dict查找子域名，确认是否创建成功
    domain = domains['name']
    if domain == RecordName:
        id = domains['id']
        ip = domains['content']
        #log.logger.info('新的DNS记录创建成功，当前ID：' + str(id))
        log.logger.info('新的DNS记录创建成功，当前IP：' + str(ip))
        return (id, ip)
    else:
        log.logger.info('新的DNS记录创建失败')



# 获取公网IP地址
def get_public_ip():
    from requests_toolbelt.adapters import source
    s = requests.Session()
    yitai_ip = source.SourceAddressAdapter(Settings_network)
    s.mount('http://', yitai_ip)
    url = 'http://ipv4.icanhazip.com'
    response = s.get(url)
    
    try:
        response.raise_for_status()
        ip = response.text.strip()  # 清除空白字符
        return ip
    except requests.exceptions.RequestException as e:
        log.logger.error(f"Failed to get public IP: {e}")
        return None

def save_ip_to_file(ip, ipfile):
    try:
        with open(ipfile, 'w') as file:
            file.write(ip)
    except Exception as e:
        log.logger.error(f"Failed to save IP to file: {e}")

# 将公网IP保存到本地文件，每次运行的时候，检查公网IP和本地记录是否一样，如果不一样，才执行API操作
def iprecord(newip):
    # 如果IP记录文件存在，执行比较
    if os.path.exists(ipfile):
        with open(ipfile, 'r') as file:
            localip = file.read()
            # 如果公网IP和本地记录不一样，返回none
            if str(newip) != str(localip):
                log.logger.info('公网IP和本地记录不一样，本地记录IP：' + localip + '， 新IP：' + str(newip))
                iprecord = 'none'
                return iprecord
            else:
                log.logger.info('公网IP和本地记录一样，本地记录IP：' + localip + '， 新IP：' + str(newip))
    else:
        with open(ipfile, 'w') as file:
            iprecord = 'none'
            return iprecord


# 获取当前公网IP，读取本地记录的IP地址，比较是否一样，IP不同就通过API查询，如果公网IP和API查询结果不一样，就修改（没有记录就创建）DNS记录
def checkip(iprecord):
    if iprecord == 'none':
        id, ip = Rget(ZoneName, ZoneId, Header)
        # 检查有没有DNS记录，没有记录就创建DNS记录，有记录比较现在的IP和记录IP是不是一样，不一样就更新DNS记录
        if  ip == newip:
            log.logger.info('新的IP和DNS记录相同，没有修改DNS记录：' + str(newip))
            with open(ipfile, 'w') as file:
                file.write(ip)
        elif ip == -1: # 如果IP为空，创建新的DNS记录
            id, ip = Rcreate(ZoneId, RecordName, newip, Header)
            #log.logger.info('当前DNS记录的ID是：' + str(id))
            log.logger.info('当前DNS记录的IP是：' + str(ip))
            with open(ipfile, 'w') as file:
                file.write(ip)
        elif ip != newip and ip != -1: # 如果IP不为空，并且和当前IP不同，更新DNS记录
            id, ip = Rupdate(ZoneId, RecordName, id, newip, Header)
            #log.logger.info('当前DNS记录的ID是：' + str(id))
            log.logger.info('当前DNS记录的IP是：' + str(ip))
            with open(ipfile, 'w') as file:
                file.write(ip)

if __name__ == '__main__':
    # 本地IP保存文件
    #ipfile = '/tmp/ip.log'  # linux
    ipfile = Settings_ipfile
    # 配置日志文件 
    # 获取当前目录
    current_dir = os.path.join(os.getcwd(), "LOG")
    # 日志文件输出和日志等级
    log = Logger(current_dir, level='info')
    # 主域名zoneid
    ZoneId = Settings_ZoneId
    # 令牌，需有dns添加，编辑，修改权限
    DnsToken = Settings_DnsToken
    # Header数据，注意Bearer后面有空格，拼接格式Bearer xxxxx....xxxxx
    Header = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + DnsToken
    }
    # 主域名和子域名
    ZoneName = Settings_network
    RecordName = Settings_subdomain
    # 获取当前最新IP
    newip = get_public_ip()
    # 比较最新获取的IP和本地IP记录，如果不同，开始通过API接口进行比较，创建，更新
    iprecord = iprecord(newip)
    # 比较最新获取的IP和DNS记录，处理更新、创建
    checkip(iprecord)

