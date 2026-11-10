#pragma once

#include <string>
#include "cJSON.h"

// 仅保存短业务回执，避免服务端异常响应耗尽 ESP32 的堆。
struct IdfPushHttpResponse {
    static constexpr size_t LIMIT = 2048;
    std::string body;
    bool overflow = false;
    bool supported = false;
    void append(const char* data, size_t size) {
        if (overflow) return;
        if (size > LIMIT - body.size()) {
            overflow = true;
            return;
        }
        body.append(data, size);
    }
};

inline bool idf_push_feishu_response_ok(const std::string& body, int& service_code)
{
    service_code = -1;
    cJSON* root = cJSON_ParseWithLengthOpts(body.c_str(), body.size() + 1, nullptr, true);
    if (!root) return false;
    bool found = false;
    bool ok = cJSON_IsObject(root);
    for (const char* name : {"code", "StatusCode"}) {
        const cJSON* value = cJSON_GetObjectItemCaseSensitive(root, name);
        if (!value) continue;
        found = true;
        if (!cJSON_IsNumber(value) || value->valuedouble != value->valueint) {
            ok = false;
            break;
        }
        service_code = value->valueint;
        if (service_code != 0) {
            ok = false;
            break;
        }
    }
    cJSON_Delete(root);
    return ok && found;
}
