#!/usr/bin/env python3
"""提取实际签名函数，验证 PSA 调用参数、已知向量和失败路径。"""
import base64
import hashlib
import hmac
import os
from pathlib import Path
import shlex
import subprocess

ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'build'/'host'
VECTORS=[('1794282249\nfeishu-local-diagnostic-key', ''), ('key', 'The quick brown fox jumps over the lazy dog'), ('xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', 'message')]

def main():
    src=(ROOT/'components/idf_push/idf_push.cpp').read_text(encoding='utf-8')
    start=src.index('static std::string hmac_sha256_base64(')
    end=src.index('\nstatic int64_t utc_millis()',start)
    helper=src[start:end]
    prefix=r"""
#include <cassert>
#include <cstdint>
#include <cstdarg>
#include <cstring>
#include <string>
#include <iostream>
using psa_status_t=int;using psa_key_id_t=unsigned;
struct psa_key_attributes_t {int unused;};
#define PSA_KEY_ATTRIBUTES_INIT {0}
#define PSA_SUCCESS 0
#define PSA_KEY_TYPE_HMAC 1
#define PSA_KEY_USAGE_SIGN_MESSAGE 2
#define PSA_ALG_SHA_256 3
#define PSA_ALG_HMAC(x) (100+(x))
static int fail_stage=0,destroyed=0;
static std::string want_key,want_data,want_digest;
static void idf_logf(const char*,...) {}
static void idf_log_line(const char*) {}
static int psa_crypto_init(){return fail_stage==1?-1:0;}
static void psa_set_key_type(psa_key_attributes_t*,int x){assert(x==PSA_KEY_TYPE_HMAC);}
static void psa_set_key_usage_flags(psa_key_attributes_t*,int x){assert(x==PSA_KEY_USAGE_SIGN_MESSAGE);}
static void psa_set_key_algorithm(psa_key_attributes_t*,int x){assert(x==PSA_ALG_HMAC(PSA_ALG_SHA_256));}
static void psa_reset_key_attributes(psa_key_attributes_t*){}
static int psa_import_key(const psa_key_attributes_t*,const uint8_t* p,size_t n,psa_key_id_t* key){assert(std::string(reinterpret_cast<const char*>(p),n)==want_key);if(fail_stage==2)return -2;*key=7;return 0;}
static int psa_mac_compute(psa_key_id_t key,int alg,const uint8_t* p,size_t n,uint8_t* out,size_t cap,size_t* olen){assert(key==7&&alg==PSA_ALG_HMAC(PSA_ALG_SHA_256));assert(std::string(reinterpret_cast<const char*>(p),n)==want_data);assert(cap>=32);if(fail_stage==3)return -3;memcpy(out,want_digest.data(),32);*olen=fail_stage==4?31:32;return 0;}
static int psa_destroy_key(psa_key_id_t key){assert(key==7);++destroyed;return 0;}
// 模拟设备上失效的旧 MD/HMAC 接口：错误不得转成全零签名。
struct mbedtls_md_context_t{};struct mbedtls_md_info_t{};
#define MBEDTLS_MD_SHA256 1
static void mbedtls_md_init(mbedtls_md_context_t*){}
static const mbedtls_md_info_t* mbedtls_md_info_from_type(int){return nullptr;}
static int mbedtls_md_setup(mbedtls_md_context_t*,const mbedtls_md_info_t*,int){return -1;}
static int mbedtls_md_hmac_starts(mbedtls_md_context_t*,const unsigned char*,size_t){return -1;}
static int mbedtls_md_hmac_update(mbedtls_md_context_t*,const unsigned char*,size_t){return -1;}
static int mbedtls_md_hmac_finish(mbedtls_md_context_t*,unsigned char*){return -1;}
static void mbedtls_md_free(mbedtls_md_context_t*){}
static int mbedtls_base64_encode(unsigned char* out,size_t cap,size_t* olen,const unsigned char* in,size_t n){
 if(fail_stage==5)return -5;
 const char* abc="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";std::string s;
 for(size_t i=0;i<n;i+=3){unsigned v=unsigned(in[i])<<16;if(i+1<n)v|=unsigned(in[i+1])<<8;if(i+2<n)v|=in[i+2];s+=abc[(v>>18)&63];s+=abc[(v>>12)&63];s+=i+1<n?abc[(v>>6)&63]:'=';s+=i+2<n?abc[v&63]:'=';}
 assert(cap>=s.size());memcpy(out,s.data(),s.size());*olen=s.size();return 0;
}
"""
    cases=[]
    import json
    for key,data in VECTORS:
        digest=hmac.new(key.encode(),data.encode(),hashlib.sha256).digest()
        hexstr=','.join('char(0x%02x)'%v for v in digest)
        cases.append('want_key='+json.dumps(key)+';want_data='+json.dumps(data)+';want_digest=std::string({'+hexstr+'});fail_stage=0;destroyed=0;assert(hmac_sha256_base64(want_data,want_key)=='+json.dumps(base64.b64encode(digest).decode())+');assert(destroyed==1);')
    cases.append('for(int stage=1;stage<=5;++stage){fail_stage=stage;destroyed=0;assert(hmac_sha256_base64(want_data,want_key).empty());assert(destroyed==(stage>=3?1:0));}')
    BUILD.mkdir(parents=True,exist_ok=True)
    cpp=BUILD/'test_push_signing.cpp';exe=BUILD/'test_push_signing'
    cpp.write_text(prefix+'\n'+helper+'\nint main(){\n'+'\n'.join(cases)+'\nstd::cout<<"push signing: 3 vectors + 5 failure paths passed\\n";}',encoding='utf-8')
    subprocess.run(shlex.split(os.environ.get('CXX','c++'))+['-std=c++17','-Wall','-Wextra','-Wno-unused-function',str(cpp),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
if __name__=='__main__':main()
