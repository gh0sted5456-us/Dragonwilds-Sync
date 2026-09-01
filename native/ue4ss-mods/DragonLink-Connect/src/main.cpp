#define NOMINMAX
#include <Windows.h>

#include <algorithm>
#include <bit>
#include <cctype>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <string>
#include <vector>

#include <DynamicOutput/DynamicOutput.hpp>
#include <Mod/CppUserModBase.hpp>
#include <Unreal/CoreUObject/UObject/UnrealType.hpp>
#include <Unreal/Hooks/Hooks.hpp>
#include <Unreal/UObject.hpp>
#include <Unreal/UObjectArray.hpp>
#include <UEngine.hpp>

namespace
{
    using namespace RC;
    using namespace RC::Unreal;

    struct Config { bool enabled{true}; std::wstring ip; std::wstring password; };

    std::filesystem::path mod_root()
    {
        HMODULE module{};
        GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           reinterpret_cast<LPCWSTR>(&mod_root), &module);
        wchar_t path[MAX_PATH]{};
        GetModuleFileNameW(module, path, MAX_PATH);
        return std::filesystem::path(path).parent_path().parent_path();
    }

    Config load_config()
    {
        Config result;
        std::wifstream input(mod_root() / "DragonLink.ini");
        bool connect = false;
        for (std::wstring line; std::getline(input, line);)
        {
            auto lower = line;
            std::transform(lower.begin(), lower.end(), lower.begin(), [](wchar_t c) { return std::towlower(c); });
            if (lower.find(L'[') != std::wstring::npos) { connect = lower.find(L"[connect]") != std::wstring::npos; continue; }
            if (!connect) continue;
            auto equals = line.find(L'='); if (equals == std::wstring::npos) continue;
            auto key = lower.substr(0, equals); auto value = line.substr(equals + 1);
            if (key.find(L"enabled") != std::wstring::npos) result.enabled = lower.substr(equals + 1).find(L"false") == std::wstring::npos;
            else if (key.find(L"password") != std::wstring::npos) result.password = value;
            else if (key.find(L"ip") != std::wstring::npos) result.ip = value;
        }
        return result;
    }

    class DragonLinkConnectMod final : public CppUserModBase, public FUObjectCreateListener
    {
        Config m_config{};
        std::mutex m_mutex;
        std::vector<std::pair<UObject*, int>> m_pending;
        Hook::GlobalCallbackId m_tick_id{};
        bool m_listening{};

        static bool direct_widget(const std::string& name)
        {
            auto value = name;
            std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
            return value.find("default__") == std::string::npos && value.find("directpanel") != std::string::npos &&
                   (value.find("editabletext") != std::string::npos || value.find("editabletextbox") != std::string::npos);
        }

        void hydrate(UObject* object)
        {
            if (!object || !UObject::IsReal(object)) return;
            auto name = to_string(object->GetFullName());
            auto lowered = name;
            std::transform(lowered.begin(), lowered.end(), lowered.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
            const std::wstring* value = nullptr;
            if (lowered.find("ipaddress") != std::string::npos) value = &m_config.ip;
            else if (lowered.find("password") != std::string::npos || lowered.find("passcode") != std::string::npos || lowered.find("worldpass") != std::string::npos) value = &m_config.password;
            if (!value || value->empty()) return;
            auto* property = object->GetPropertyByNameInChain(STR("Text"));
            if (!property) return;
            void* target = property->ContainerPtrToValuePtr<void>(object);
            property->ImportText(value->c_str(), target, 0, object, nullptr);
            if (auto* sync = object->GetFunctionByNameInChain(STR("SynchronizeProperties"))) object->ProcessEvent(sync, nullptr);
            Output::send(STR("[DragonLink-Connect] Hydrated {} exactly once.\n"), object->GetFullName());
        }

      public:
        DragonLinkConnectMod()
        {
            ModName = STR("DragonLink-Connect"); ModAuthors = STR("Dragonwilds Sync");
            ModDescription = STR("One-shot Direct Connect credential hydration"); ModVersion = STR("1.0.0");
        }
        ~DragonLinkConnectMod() override
        {
            if (m_tick_id) Hook::UnregisterCallback(m_tick_id);
            if (m_listening) UObjectArray::RemoveUObjectCreateListener(this);
        }
        void on_unreal_init() override
        {
            m_config = load_config(); if (!m_config.enabled) return;
            UObjectArray::AddUObjectCreateListener(this);
            m_listening = true;
            m_tick_id = Hook::RegisterEngineTickPreCallback([this](auto&, UEngine*, float, bool) {
                std::scoped_lock lock(m_mutex);
                for (auto it = m_pending.begin(); it != m_pending.end();) {
                    if (--it->second <= 0) { hydrate(it->first); it = m_pending.erase(it); } else ++it;
                }
            }, {false, false, STR("DragonLink-Connect"), STR("OneShotHydration")});
            Output::send(STR("[DragonLink-Connect] Creation observer active; no polling enabled.\n"));
        }
        void NotifyUObjectCreated(const UObjectBase* object, int32) override
        {
            auto* candidate = std::bit_cast<UObject*>(object);
            if (!candidate || !direct_widget(to_string(candidate->GetFullName()))) return;
            std::scoped_lock lock(m_mutex); m_pending.emplace_back(candidate, 12);
        }
        void OnUObjectArrayShutdown() override
        {
            if (m_listening) { UObjectArray::RemoveUObjectCreateListener(this); m_listening = false; }
        }
    };
}

extern "C"
{
    __declspec(dllexport) RC::CppUserModBase* start_mod() { return new DragonLinkConnectMod(); }
    __declspec(dllexport) void uninstall_mod(RC::CppUserModBase* mod) { delete mod; }
}
