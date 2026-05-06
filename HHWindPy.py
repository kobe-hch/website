import urllib.request
import urllib.parse
import json
import pandas as pd
from io import StringIO

# 定义服务器地址
SERVER_URL = 'http://10.5.5.230:8080'

def wsd(*args,**kwargs):
    kwargs["usedf"]=True
    return send_get_request("wsd",*args,**kwargs)
def wss(*args,**kwargs):
    kwargs["usedf"]=True
    return send_get_request("wss",*args,**kwargs)
def wst(*args,**kwargs):
    kwargs["usedf"]=True
    return send_get_request("wst",*args,**kwargs)
def wsi(*args,**kwargs):
    kwargs["usedf"]=True
    return send_get_request("wsi",*args,**kwargs)
def wsq(*args,**kwargs):
    kwargs["usedf"]=True
    return send_get_request("wsq",*args,**kwargs)
def wsee(*args,**kwargs):
    kwargs["usedf"]=True
    return send_get_request("wsee",*args,**kwargs)
def wses(*args,**kwargs):
    kwargs["usedf"]=True
    return send_get_request("wses",*args,**kwargs)
def wset(*args,**kwargs):
    kwargs["usedf"]=True
    return send_get_request("wset",*args,**kwargs)
def edb(*args,**kwargs):
    kwargs["usedf"]=True
    return send_get_request("edb",*args,**kwargs)


from collections import namedtuple
class wdata(namedtuple('wdataBase', ['ErrorCode', 'dfData', 'Times', 'Data'])):
    ...
    
# 1. 发送GET请求
def send_get_request(method,*args,**kwargs):
    try:
        # 构造请求（可添加查询参数）
        params = {'method': method, 'args': args, 'kwargs': kwargs}
        query_string = urllib.parse.urlencode(params)
        full_url = f"{SERVER_URL}?{query_string}"
        
        # 发送GET请求
        with urllib.request.urlopen(full_url) as response:
            # 读取响应数据
            response_body = response.read()
            # 解析响应JSON
            df = pd.read_json(StringIO(response_body.decode('utf-8')),convert_dates=['tradedate'])
            
        #print("=== GET请求响应结果 ===")
        #print(f"响应状态码：{response.getcode()}")
        #print(f"响应数据：{df}")
        
        errorCode = response.getcode()
        if errorCode==200: errorCode = 0
        return wdata(errorCode,df,df.index.tolist(),df.T.values.tolist())
    
    except Exception as e:
        print(f"GET请求失败：{e}")

if __name__ == '__main__':
    send_get_request("wset","indexhistory","startdate=2025-01-01;enddate=2025-12-31;windcode=000016.SH;field=tradedate,tradecode,tradestatus")