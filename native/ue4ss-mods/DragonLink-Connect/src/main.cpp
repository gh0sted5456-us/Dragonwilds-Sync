#define NOMINMAX
#include <Windows.h>

#include <algorithm>
#include <bit>
#include <cctype>
#include <cwctype>
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

    std::wstring trim(std::wstring value)
    {
        const auto whitespace = [](wchar_t c) { return std::iswspace(c) != 0; };
        value.erase(value.begin(), std::find_if(value.begin(), value.end(), [&](wchar_t c) { return !whitespace(c); }));
        value.erase(std::find_if(value.rbegin(), value.rend(), [&](wchar_t c) { return !whitespace(c); }).base(), value.end());
        if (value.size() >= 2 && ((value.front() == L'"' && value.back() == L'"') || (value.front() == L'\'' && value.back() == L'\'')))
            value = value.substr(1, value.size() - 2);
        return value;
    }

    Config load_config()
    {
        Config result;
        const auto path = mod_root() / "DragonLink.ini";
        std::wifstream input(path);
        bool connect = false;
        for (std::wstring line; std::getline(input, line);)
        {
            auto lower = line;
            std::transform(lower.begin(), lower.end(), lower.begin(), [](wchar_t c) { return std::towlower(c); });
            if (lower.find(L'[') != std::wstring::npos) { connect = lower.find(L"[connect]") != std::wstring::npos; continue; }
            if (!connect) continue;
            auto equals = line.find(L'='); if (equals == std::wstring::npos) continue;
            auto key = trim(lower.substr(0, equals)); auto value = trim(line.substr(equals + 1));
            auto lowered_value = value;
            std::transform(lowered_value.begin(), lowered_value.end(), lowered_value.begin(), [](wchar_t c) { return std::towlower(c); });
            if (key == L"enabled") result.enabled = lowered_value != L"false" && lowered_value != L"0" && lowered_value != L"no";
            else if (key == L"password") result.password = value;
            else if (key == L"ip" || key == L"address") result.ip = value;
        }
        return result;
    }

    enum class CredentialField { none, address, password };

    CredentialField credential_field(const std::string& name)
    {
        auto value = name;
        std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
        if (value.find("default__") != std::string::npos) return CredentialField::none;
        if (value.find("editabletext") == std::string::npos && value.find("editabletextbox") == std::string::npos)
            return CredentialField::none;

        const bool connect_surface = value.find("direct") != std::string::npos || value.find("connect") != std::string::npos ||
                                     value.find("join") != std::string::npos || value.find("server") != std::string::npos;
        if (!connect_surface) return CredentialField::none;

        if (value.find("ipaddress") != std::string::npos || value.find("serveraddress") != std::string::npos ||
            value.find("serverip") != std::string::npos || value.find("address") != std::string::npos ||
            value.find("endpoint") != std::string::npos)
            return CredentialField::address;
        if (value.find("password") != std::string::npos || value.find("passcode") != std::string::npos ||
            value.find("worldpass") != std::string::npos)
            return CredentialField::password;
        return CredentialField::none;
    }

    class DragonLinkConnectMod final : public CppUserModBase, public FUObjectCreateListener
    {
        struct Pending { UObject* object{}; CredentialField field{CredentialField::none}; int ticks{}; int attempts{}; };

        Config m_config{};
        std::mutex m_mutex;
        std::vector<Pending> m_pending;
        Hook::GlobalCallbackId m_tick_id{};
        bool m_listening{};

        bool hydrate(UObject* object, CredentialField field)
        {
            if (!object || !UObject::IsReal(object)) return false;
            const std::wstring* value = field == CredentialField::address ? &m_config.ip :
                                        field == CredentialField::password ? &m_config.password : nullptr;
            if (!value || value->empty()) return false;
            auto* property = object->GetPropertyByNameInChain(STR("Text"));
            if (!property) return false;
            void* target = property->ContainerPtrToValuePtr<void>(object);
            if (!target) return false;
            property->ImportText(value->c_str(), target, 0, object, nullptr);
            if (auto* sync = object->GetFunctionByNameInChain(STR("SynchronizeProperties"))) object->ProcessEvent(sync, nullptr);
            Output::send(STR("[DragonLink-Connect] Hydrated {} credential field.\n"), object->GetFullName());
            return true;
        }

      public:
        DragonLinkConnectMod()
        {
            ModName = STR("DragonLink-Connect"); ModAuthors = STR("Dragonwilds Sync");
            ModDescription = STR("Direct Connect credential hydration"); ModVersion = STR("1.1.0");
        }
        ~DragonLinkConnectMod() override
        {
            if (m_tick_id) Hook::UnregisterCallback(m_tick_id);
            if (m_listening) UObjectArray::RemoveUObjectCreateListener(this);
        }
        void on_unreal_init() override
        {
            m_config = load_config();
            if (!m_config.enabled || m_config.ip.empty()) {
                Output::send(STR("[DragonLink-Connect] Disabled or no configured address in DragonLink.ini.\n"));
                return;
            }
            UObjectArray::AddUObjectCreateListener(this);
            m_listening = true;
            m_tick_id = Hook::RegisterEngineTickPreCallback([this](auto&, UEngine*, float, bool) {
                std::scoped_lock lock(m_mutex);
                for (auto it = m_pending.begin(); it != m_pending.end();) {
                    if (--it->ticks > 0) { ++it; continue; }
                    const bool applied = hydrate(it->object, it->field);
                    ++it->attempts;
                    if (applied || it->attempts >= 4 || !it->object || !UObject::IsReal(it->object)) {
                        it = m_pending.erase(it);
                    } else {
                        // Some UMG widgets expose Text a few frames after construction.
                        it->ticks = 6;
                        ++it;
                    }
                }
            }, {false, false, STR("DragonLink-Connect"), STR("CredentialHydration")});
            Output::send(STR("[DragonLink-Connect] Observer active. Password handoff: {}.\n"),
                         m_config.password.empty() ? STR("no") : STR("yes"));
        }
        void NotifyUObjectCreated(const UObjectBase* object, int32) override
        {
            auto* candidate = std::bit_cast<UObject*>(object);
            if (!candidate) return;
            const auto field = credential_field(to_string(candidate->GetFullName()));
            if (field == CredentialField::none) return;
            std::scoped_lock lock(m_mutex);
            m_pending.push_back({candidate, field, 4, 0});
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
