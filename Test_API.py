# encoding:utf-8
# __author__:DeyLies,WangYu
import requests
print("*"*20)
print("开始接口测试：")
print("time",requests.get("http://localhost:12345/time").json())
print("inventory",requests.get("http://localhost:12345/inventory").json())
print("hospotals",requests.get("http://localhost:12345/hospotals").json())
print("step_time",requests.post("http://localhost:12345/step_time",json=1000).json())
print("flight",requests.post("http://localhost:12345/flight",json= {"hospital": 1, "products": [1,9,9]}).json())
print("confirm",requests.post("http://localhost:12345/flight/3/confirm").json())
print("cancel",requests.post("http://localhost:12345/flight/5/cancel").json())
print("get",requests.get("http://localhost:12345/flight/5").json())