#define NOMINMAX
#include <Windows.h>

#include <algorithm>
#include <cctype>
#include <filesystem>
#include <fstream>
#include <string>
#include <unordered_map>

#include <DynamicOutput/DynamicOutput.hpp>
#include <Mod/CppUserModBase.hpp>
#include <Unreal/CoreUObject/UObject/UnrealType.hpp>
#include <Unreal/UObjectGlobals.hpp>
#include <Unreal/UFunctionStructs.hpp>

namespace
{
    using namespace RC;
    using namespace RC::Unreal;

    std::string json_escape(const std::string& value)
    {
        std::string out;
        out.reserve(value.size() + 8);
        for (unsigned char c : value)
        {
            switch (c)
            {
            case '\\': out += "\\\\"; break;
            case '"': out += "\\\""; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default: if (c >= 0x20) out += static_cast<char>(c); break;
            }
        }
        return out;
    }

    std::filesystem::path mod_root()
    {
        HMODULE module{};
        GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           reinterpret_cast<LPCWSTR>(&mod_root), &module);
        wchar_t path[MAX_PATH]{};
        GetModuleFileNameW(module, path, MAX_PATH);
        return std::filesystem::path(path).parent_path().parent_path();
    }

    bool enabled()
    {
        std::ifstream input(mod_root() / "DragonLink.ini");
        bool in_chat = false;
        for (std::string line; std::getline(input, line);)
        {
            if (line.find('[') != std::string::npos) {
                auto lowered = line;
                std::transform(lowered.begin(), lowered.end(), lowered.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
                in_chat = lowered.find("[chat]") != std::string::npos;
                continue;
            }
            if (!in_chat) continue;
            auto equals = line.find('=');
            if (equals == std::string::npos) continue;
            auto key = line.substr(0, equals);
            auto value = line.substr(equals + 1);
            std::transform(key.begin(), key.end(), key.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
            std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
            if (key.find("captureplayermessages") != std::string::npos) return value.find("false") == std::string::npos && value.find('0') == std::string::npos;
        }
        return true;
    }

    std::unordered_map<std::string, std::string> export_chat_fields(UnrealScriptFunctionCallableContext& context)
    {
        std::unordered_map<std::string, std::string> result;
        auto* function = context.TheStack.Node();
        if (!function || !context.TheStack.Locals()) return result;
        for (FProperty* parameter : TFieldRange<FProperty>(function, EFieldIterationFlags::IncludeDeprecated))
        {
            if (!parameter->HasAnyPropertyFlags(CPF_Parm)) continue;
            auto* struct_property = CastField<FStructProperty>(parameter);
            if (!struct_property) continue;
            void* struct_value = parameter->ContainerPtrToValuePtr<void>(context.TheStack.Locals());
            auto* definition = static_cast<UStruct*>(struct_property->GetStruct().Get());
            if (!definition || !struct_value) continue;
            for (FProperty* field : TFieldRange<FProperty>(definition, EFieldIterationFlags::IncludeDeprecated))
            {
                FString text{};
                void* value = field->ContainerPtrToValuePtr<void>(struct_value);
                field->ExportTextItem(text, value, value, context.Context, 0);
                result[to_string(field->GetName())] = to_string(*text);
            }
        }
        return result;
    }

    std::string pick(const std::unordered_map<std::string, std::string>& fields, const char* name)
    {
        auto found = fields.find(name);
        return found == fields.end() ? std::string{} : found->second;
    }

    class DragonLinkChatMod final : public CppUserModBase
    {
        RC::StringType m_hook_name{};
        std::pair<int, int> m_hook_ids{};
        bool m_registered{};

      public:
        DragonLinkChatMod()
        {
            ModName = STR("DragonLink-Chat");
            ModAuthors = STR("Dragonwilds Sync");
            ModDescription = STR("Dedicated-server game chat event bridge");
            ModVersion = STR("1.0.1");
        }

        ~DragonLinkChatMod() override
        {
            if (m_registered) UObjectGlobals::UnregisterHook(m_hook_name, m_hook_ids);
        }

        void on_unreal_init() override
        {
            if (!enabled()) { Output::send(STR("[DragonLink-Chat] Disabled by config.\n")); return; }
            auto receive = [](UnrealScriptFunctionCallableContext& context, void*) {
                auto fields = export_chat_fields(context);
                auto body = pick(fields, "MessageBody");
                if (body.empty()) return;
                const auto escaped_body = json_escape(body);
                Output::send(STR("[DragonLink-Chat] {{\"schema\":\"DragonLink.Chat.v1\",\"direction\":\"player_to_server\",\"sender_id\":\"{}\",\"character_guid\":\"{}\",\"player_id\":\"{}\",\"body\":\"{}\",\"message\":\"{}\"}}\n"),
                             ensure_str(json_escape(pick(fields, "SenderId"))),
                             ensure_str(json_escape(pick(fields, "CharacterGuid"))),
                             ensure_str(json_escape(pick(fields, "PlayerId"))),
                             ensure_str(escaped_body),
                             ensure_str(escaped_body));
            };
            m_hook_name = STR("/Script/JagexChatBackend.PlayerChatComponent:Server_SendChatMessage");
            m_hook_ids = UObjectGlobals::RegisterHook(m_hook_name, receive, {}, nullptr);
            m_registered = true;
            Output::send(STR("[DragonLink-Chat] Server chat bridge active; emitting DragonLink.Chat.v1 records.\n"));
        }
    };
}

extern "C"
{
    __declspec(dllexport) RC::CppUserModBase* start_mod() { return new DragonLinkChatMod(); }
    __declspec(dllexport) void uninstall_mod(RC::CppUserModBase* mod) { delete mod; }
}
