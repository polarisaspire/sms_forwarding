#!/usr/bin/env python3
"""回归真实射频恢复函数及硬重启/延迟恢复入口，避免重启后停留 CFUN=0。"""
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
def function(source,name):
    pos=source.find(name+'(')
    assert pos>=0, '尚未实现启动射频恢复: '+name
    begin=source.rfind('\n',0,pos)+1
    return source[begin:source.index('\n}',pos)+2]
def main():
    source=(ROOT/'components/idf_modem/idf_modem.cpp').read_text(encoding='utf-8')
    names=['parse_long_token','line_containing','parse_cfun','apply_configured_data_mode_once','process_data_mode_retry','ensure_modem_radio_ready','recover_startup_radio_if_pending','process_startup_radio_recovery','handle_reset_request_if_any','run_pending_reinit_if_recovered']
    functions='\n\n'.join(function(source,n) for n in names)
    startup=source[source.index('static void modem_task('):]
    assert startup.index('ensure_modem_radio_ready()')<startup.index('try_unlock_sim(false)')
    assert "run_pending_reinit_if_recovered();\n        process_startup_radio_recovery();" in startup
    code=r"""
#include <atomic>
#include <cassert>
#include <cctype>
#include <cerrno>
#include <cstdlib>
#include <deque>
#include <iostream>
#include <string>
#include <vector>
using std::string;
struct Step{string cmd;bool ok;string response;};
static std::deque<Step> steps;
static std::vector<string> commands;
static string idf_util_trim_copy(string s){auto a=s.find_first_not_of(" \r\n\t");if(a==string::npos)return {};return s.substr(a,s.find_last_not_of(" \r\n\t")-a+1);}
static bool send_ok(const char* cmd,unsigned=1000,string* out=nullptr){commands.push_back(cmd);assert(!steps.empty());auto s=steps.front();steps.pop_front();assert(s.cmd==cmd);if(out)*out=s.response;return s.ok;}
static void idf_log_line(const char*){}
static void idf_logf(const char*,...){}
struct IdfModemStatus{bool started=false,atReady=false,modemReady=false;string phase;int ceregStat=-1;};
static IdfModemStatus status;
static void update_status(const IdfModemStatus& p){status=p;}
struct IdfSimSettingsView{bool dataEnabled=false,roamingEnabled=false;string apn;};
static IdfModemStatus idf_modem_get_status(){return status;}
static bool parse_cereg(const string& s,int& stat){if(s=="registered")stat=1;else if(s=="roaming")stat=5;else if(s=="searching")stat=2;else return false;return true;}
static bool apn_valid_for_at(const string&){return true;}
static void set_status_cell_ip(const char*){}
static bool sample_cell_ip_once(){return true;}
static void set_phase(const char* p){status.phase=p;}
static void reset_identity_sampling_state(){}
static int power_cycles=0,configs=0,data_modes=0,unlocks=0;
static bool at_ready=true,idle=true;
static void modem_power_cycle(){++power_cycles;}
static bool wait_at_ready(){return at_ready;}
static bool try_unlock_sim(bool){++unlocks;return true;}
static bool configure_sms_and_registration(){++configs;return true;}
static void apply_startup_data_mode(){++data_modes;}
static bool at_channel_idle_now(){return idle;}
static std::atomic<int> s_esim_operation_depth{0},s_reset_request{0};
using TickType_t=unsigned;
static TickType_t s_next_radio_startup_check=0;
static bool s_reinit_pending=false,s_radio_startup_pending=true;
#define pdMS_TO_TICKS(x) (x)
static void vTaskDelay(int){}
static int data_retry_schedules=0;
static void schedule_data_mode_retry(){++data_retry_schedules;}
static int tick=0,s_next_data_mode_retry=0,s_data_mode_retry_count=0;
static bool s_data_mode_retry_pending=false;
static constexpr int MODEM_DATA_MODE_RETRY_GAP_MS=30000,MODEM_DATA_MODE_RETRY_MAX=3;
static int xTaskGetTickCount(){return tick;}
static IdfSimSettingsView idf_config_get_sim_settings_view(){return {};}

"""
    tests=r"""
static void reset(){steps.clear();commands.clear();configs=data_modes=unlocks=power_cycles=data_retry_schedules=0;at_ready=idle=true;s_reinit_pending=false;s_radio_startup_pending=true;s_next_radio_startup_check=0;tick=0;s_reset_request=0;s_esim_operation_depth=0;}
static void radio_steps(int mode){steps.push_back({"AT+CFUN?",true,"\r\n+CFUN: "+std::to_string(mode)+"\r\nOK\r\n"});if(mode!=1){steps.push_back({"AT+CFUN=1",true,"OK"});steps.push_back({"AT+CFUN?",true,"+CFUN: 1\r\nOK"});}}
int main(){
 IdfSimSettingsView cfg;
 for(string r:{"searching","OK",""}){reset();status.ceregStat=1;steps.push_back({"AT+CEREG?",true,r});assert(!apply_configured_data_mode_once(cfg,6000,2500));assert(commands.size()==1&&steps.empty());}
 reset();steps.push_back({"AT+CEREG?",false,"ERROR"});assert(!apply_configured_data_mode_once(cfg,6000,2500));assert(commands.size()==1);
 for(string r:{"registered","roaming"}){reset();steps.push_back({"AT+CEREG?",true,r});steps.push_back({"AT+CGACT=0,1",true,"OK"});assert(apply_configured_data_mode_once(cfg,6000,2500));assert(steps.empty());}
 reset();cfg.dataEnabled=true;steps.push_back({"AT+CEREG?",true,"registered"});steps.push_back({"AT+CGACT=1,1",true,"OK"});assert(apply_configured_data_mode_once(cfg,6000,2500));assert(steps.empty());
 reset();s_data_mode_retry_pending=true;s_data_mode_retry_count=0;s_next_data_mode_retry=0;tick=0;
 for(int n=0;n<5;++n){steps.push_back({"AT+CEREG?",true,"searching"});assert(process_data_mode_retry());assert(s_data_mode_retry_pending&&s_data_mode_retry_count==0);tick+=MODEM_DATA_MODE_RETRY_GAP_MS;}
 steps.push_back({"AT+CEREG?",true,"registered"});steps.push_back({"AT+CGACT=0,1",true,"OK"});assert(process_data_mode_retry());assert(!s_data_mode_retry_pending&&steps.empty());
 int mode=-1;assert(parse_cfun("AT+CFUN?\r\n+CEREG: 0\r\n+CFUN: 1\r\nOK",mode)&&mode==1);
 assert(!parse_cfun("+CFUN: 1garbage\r\nOK",mode));assert(!parse_cfun("+CFUN: -1\r\nOK",mode));
 for(int m:{0,1,4}){reset();radio_steps(m);assert(ensure_modem_radio_ready());assert(steps.empty());assert(commands.size()==(m==1?1u:3u));}
 reset();steps.push_back({"AT+CFUN?",false,"ERROR"});assert(!ensure_modem_radio_ready());assert(commands.size()==1);
 reset();steps.push_back({"AT+CFUN?",true,"OK"});assert(!ensure_modem_radio_ready());assert(commands.size()==1);
 reset();steps.push_back({"AT+CFUN?",true,"+CFUN: 0"});steps.push_back({"AT+CFUN=1",false,"ERROR"});assert(!ensure_modem_radio_ready());assert(steps.empty());
 reset();steps.push_back({"AT+CFUN?",true,"+CFUN: 0"});steps.push_back({"AT+CFUN=1",true,"OK"});steps.push_back({"AT+CFUN?",true,"+CFUN: 0"});assert(!ensure_modem_radio_ready());
 reset();s_reset_request=2;radio_steps(0);assert(handle_reset_request_if_any());assert(power_cycles==1&&configs==1&&unlocks==1&&data_modes==1&&!s_reinit_pending&&steps.empty());
 reset();s_reset_request=2;steps.push_back({"AT+CFUN?",false,"ERROR"});assert(handle_reset_request_if_any());assert(s_reinit_pending&&configs==0&&unlocks==0);steps.push_back({"AT",true,"OK"});radio_steps(0);run_pending_reinit_if_recovered();assert(!s_reinit_pending&&configs==1&&unlocks==1&&data_modes==1&&steps.empty());
 reset();s_reinit_pending=true;steps.push_back({"AT",true,"OK"});steps.push_back({"AT+CFUN?",true,"OK"});run_pending_reinit_if_recovered();assert(s_reinit_pending&&configs==0&&unlocks==0);
 reset();s_reinit_pending=true;idle=false;run_pending_reinit_if_recovered();assert(s_reinit_pending&&commands.empty());
 reset();s_reset_request=2;s_esim_operation_depth=1;assert(!handle_reset_request_if_any());assert(s_reset_request==2&&commands.empty());
 reset();run_pending_reinit_if_recovered();assert(commands.empty());
 reset();radio_steps(0);recover_startup_radio_if_pending(0);assert(s_radio_startup_pending&&steps.empty()&&data_retry_schedules==1);radio_steps(0);recover_startup_radio_if_pending(0);assert(steps.empty());recover_startup_radio_if_pending(1);assert(!s_radio_startup_pending);commands.clear();recover_startup_radio_if_pending(0);assert(commands.empty());
 reset();steps.push_back({"AT+CFUN?",true,"+CFUN: 4"});recover_startup_radio_if_pending(0);assert(commands.size()==1&&steps.empty());

 reset();idle=false;process_startup_radio_recovery();assert(commands.empty());idle=true;radio_steps(0);process_startup_radio_recovery();assert(steps.empty()&&s_radio_startup_pending);commands.clear();tick=1000;process_startup_radio_recovery();assert(commands.empty());tick=5000;radio_steps(0);process_startup_radio_recovery();assert(steps.empty());recover_startup_radio_if_pending(1);commands.clear();tick=10000;process_startup_radio_recovery();assert(commands.empty());
 std::cout<<"radio startup: registered-only PDP config (including stale cache), mode recovery, failed/partial replies, reset recovery, APDU exclusion and normal-runtime checks passed"<<std::endl;
}
"""
    build=ROOT/'build'/'host';build.mkdir(parents=True,exist_ok=True)
    cpp=build/'test_modem_radio_startup.cpp';exe=build/'test_modem_radio_startup';cpp.write_text(code+'\n'+functions+'\n'+tests,encoding='utf-8')
    subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror',str(cpp),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
if __name__=='__main__':main()
