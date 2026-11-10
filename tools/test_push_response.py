#!/usr/bin/env python3
"""用实际 cJSON 解析器验证飞书业务状态与有界响应缓存。"""
import os,json,shlex,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'build'/'host'
CASES=[('{"code":0,"msg":"success"}',True,0),('{"StatusCode":0}',True,0),('{"code":0,"StatusCode":0}',True,0),('{"code":19021}',False,19021),('{"code":19024}',False,19024),('{"code":0,"StatusCode":19021}',False,19021),('{"data":{"code":0}}',False,-1),('{"code":"0"}',False,-1),('{"code":0.5}',False,-1),('{"code":false}',False,-1),('{"code":0}junk',False,-1),('{}',False,-1),('',False,-1),('not json',False,-1)]
def main():
    header=ROOT/'components/idf_push/include/idf_push_feishu_response.h'
    assert header.exists(), '飞书业务响应校验尚未实现'
    cjson=Path(os.environ['CJSON_SOURCE'])
    code='#include <cassert>\n#include <iostream>\n#include "idf_push_feishu_response.h"\nint main(){int code=-1;\n'
    for body,ok,status in CASES:
        code+='assert(idf_push_feishu_response_ok('+json.dumps(body)+',code)=='+str(ok).lower()+');assert(code=='+str(status)+');\n'
    code+='IdfPushHttpResponse r;r.append("12345",5);r.append("67890",5);assert(r.body=="1234567890"&&!r.overflow);r.append(std::string(2048,char(120)).data(),2048);assert(r.overflow&&r.body.size()<=2048);const auto size=r.body.size();r.append("x",1);assert(r.body.size()==size);std::cout<<"push response: 14 API cases + bounded chunk capture passed"<<std::endl;}'
    BUILD.mkdir(parents=True,exist_ok=True);cpp=BUILD/'test_push_response.cpp';exe=BUILD/'test_push_response';cpp.write_text(code,encoding='utf-8')
    subprocess.run(shlex.split(os.environ.get('CXX','c++'))+['-std=c++17','-Wall','-Wextra','-Werror','-I',str(header.parent),'-I',str(cjson),str(cpp),str(cjson/'cJSON.c'),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
if __name__=='__main__':main()
