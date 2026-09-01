#define NOMINMAX
#include <Windows.h>

#include <algorithm>
#include <cctype>
#include <filesystem>
#include <fstream>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

#include <DynamicOutput/DynamicOutput.hpp>
#include <Mod/CppUserModBase.hpp>
#include <Unreal/UObject.hpp>
#include <Unreal/UObjectGlobals.hpp>
#include <Unreal/UFunctionStructs.hpp>

namespace
{
    using namespace RC;
    using namespace RC::Unreal;

    struct Config
    {
        bool enabled{true};
        bool stacks{true};
        bool weights{true};
        std::unordered_map<std::string, int32_t> stack_rules;
        std::unordered_map<std::string, float> weight_rules;
    };

    std::string trim(std::string value)
    {
        auto visible = [](unsigned char c) { return !std::isspace(c); };
        value.erase(value.begin(), std::find_if(value.begin(), value.end(), visible));
        value.erase(std::find_if(value.rbegin(), value.rend(), visible).base(), value.end());
        return value;
    }

    std::string lower(std::string value)
    {
        std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
        return value;
    }

    bool wildcard_match(std::string pattern, std::string value)
    {
        pattern = lower(pattern); value = lower(value);
        size_t p = 0, v = 0, star = std::string::npos, retry = 0;
        while (v < value.size())
        {
            if (p < pattern.size() && (pattern[p] == '?' || pattern[p] == value[v])) { ++p; ++v; }
            else if (p < pattern.size() && pattern[p] == '*') { star = p++; retry = v; }
            else if (star != std::string::npos) { p = star + 1; v = ++retry; }
            else { return false; }
        }
        while (p < pattern.size() && pattern[p] == '*') { ++p; }
        return p == pattern.size();
    }

    std::filesystem::path mod_root()
    {
        HMODULE module{};
        GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           reinterpret_cast<LPCWSTR>(&mod_root), &module);
        wchar_t path[MAX_PATH]{}; GetModuleFileNameW(module, path, MAX_PATH);
        return std::filesystem::path(path).parent_path().parent_path();
    }

    bool dedicated_server_process()
    {
        wchar_t path[MAX_PATH]{}; GetModuleFileNameW(nullptr, path, MAX_PATH);
        auto name = lower(std::filesystem::path(path).filename().string());
        return name.find("server") != std::string::npos;
    }

    Config load_config()
    {
        Config result; std::ifstream input(mod_root() / "DragonLink.ini"); std::string section;
        for (std::string line; std::getline(input, line);)
        {
            line = trim(line);
            if (line.empty() || line[0] == ';' || line[0] == '#') { continue; }
            if (line.front() == '[' && line.back() == ']') { section = lower(trim(line.substr(1, line.size() - 2))); continue; }
            auto equals = line.find('='); if (equals == std::string::npos) { continue; }
            auto key = trim(line.substr(0, equals)); auto value = trim(line.substr(equals + 1));
            try
            {
                if (section == "stacksweights")
                {
                    auto flag = lower(value) == "true" || value == "1" || lower(value) == "yes";
                    if (lower(key) == "enabled") result.enabled = flag;
                    else if (lower(key) == "stacks") result.stacks = flag;
                    else if (lower(key) == "weights") result.weights = flag;
                }
                else if (section == "stacks") result.stack_rules[key] = static_cast<int32_t>(std::stol(value));
                else if (section == "weights") result.weight_rules[key] = std::stof(value);
            }
            catch (...) { Output::send<LogLevel::Warning>(STR("[DragonLink-StacksWeights] Ignored invalid config rule.\n")); }
        }
        return result;
    }

    template <typename T>
    std::optional<T> find_rule(const std::unordered_map<std::string, T>& rules, const std::string& item)
    {
        auto exact = rules.find(item); if (exact != rules.end()) return exact->second;
        for (const auto& [pattern, value] : rules) if (wildcard_match(pattern, item)) return value;
        return std::nullopt;
    }

    class DragonLinkStacksWeightsMod final : public CppUserModBase
    {
        Config m_config{}; bool m_server{};
        std::vector<std::pair<RC::StringType, std::pair<int, int>>> m_hooks;
      public:
        DragonLinkStacksWeightsMod()
        {
            ModName = STR("DragonLink-StacksWeights"); ModAuthors = STR("Dragonwilds Sync");
            ModDescription = STR("Profile-owned stack and weight authority bridge"); ModVersion = STR("1.0.0");
        }
        ~DragonLinkStacksWeightsMod() override
        {
            for (const auto& [name, ids] : m_hooks) UObjectGlobals::UnregisterHook(name, ids);
        }
        void on_unreal_init() override
        {
            m_config = load_config(); m_server = dedicated_server_process();
            if (!m_config.enabled) { Output::send(STR("[DragonLink-StacksWeights] Disabled by DragonLink.ini.\n")); return; }
            auto post_stack = [this](UnrealScriptFunctionCallableContext& context, void*) {
                if (!m_server || !m_config.stacks || !context.Context || !context.RESULT_DECL) return;
                auto item = to_string(context.Context->GetFullName());
                if (auto value = find_rule(m_config.stack_rules, item)) context.SetReturnValue<int32_t>(*value);
            };
            auto post_weight = [this](UnrealScriptFunctionCallableContext& context, void*) {
                if (!m_config.weights || !context.Context || !context.RESULT_DECL) return;
                auto item = to_string(context.Context->GetFullName());
                if (auto value = find_rule(m_config.weight_rules, item)) context.SetReturnValue<float>(*value);
            };
            const RC::StringType max_stack = STR("/Script/Dominion.ItemData:GetMaxStackSize");
            const RC::StringType free_space = STR("/Script/Dominion.Item:GetStackFreeSpace");
            const RC::StringType item_weight = STR("/Script/Dominion.ItemData:GetItemWeight");
            m_hooks.emplace_back(max_stack, UObjectGlobals::RegisterHook(max_stack, {}, post_stack, nullptr));
            m_hooks.emplace_back(free_space, UObjectGlobals::RegisterHook(free_space, {}, post_stack, nullptr));
            m_hooks.emplace_back(item_weight, UObjectGlobals::RegisterHook(item_weight, {}, post_weight, nullptr));
            Output::send(STR("[DragonLink-StacksWeights] Native rules active ({}) with {} stack and {} weight rules.\n"),
                         m_server ? STR("server authority") : STR("client presentation"),
                         m_config.stack_rules.size(), m_config.weight_rules.size());
        }
    };
}

extern "C"
{
    __declspec(dllexport) RC::CppUserModBase* start_mod() { return new DragonLinkStacksWeightsMod(); }
    __declspec(dllexport) void uninstall_mod(RC::CppUserModBase* mod) { delete mod; }
}
