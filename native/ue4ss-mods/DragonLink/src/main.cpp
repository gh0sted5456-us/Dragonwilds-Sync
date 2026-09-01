#define NOMINMAX
#include <Windows.h>

#include <algorithm>
#include <cctype>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

#include <DynamicOutput/DynamicOutput.hpp>
#include <Mod/CppUserModBase.hpp>

namespace
{
    using namespace RC;
    using StartMod = CppUserModBase* (*)();
    using StopMod = void (*)(CppUserModBase*);

    struct LoadedFeature { HMODULE module{}; CppUserModBase* mod{}; StopMod stop{}; };

    std::filesystem::path module_root()
    {
        HMODULE module{};
        GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           reinterpret_cast<LPCWSTR>(&module_root), &module);
        wchar_t path[MAX_PATH]{};
        GetModuleFileNameW(module, path, MAX_PATH);
        return std::filesystem::path(path).parent_path().parent_path();
    }

    bool server_process()
    {
        wchar_t path[MAX_PATH]{};
        GetModuleFileNameW(nullptr, path, MAX_PATH);
        auto name = std::filesystem::path(path).filename().string();
        std::transform(name.begin(), name.end(), name.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
        return name.find("server") != std::string::npos;
    }

    bool feature_enabled(const std::string& wanted, bool fallback)
    {
        std::ifstream input(module_root() / "DragonLink.ini");
        bool features = false;
        for (std::string line; std::getline(input, line);)
        {
            auto lowered = line;
            std::transform(lowered.begin(), lowered.end(), lowered.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
            if (lowered.find('[') != std::string::npos) { features = lowered.find("[features]") != std::string::npos; continue; }
            if (!features) continue;
            auto equals = lowered.find('=');
            if (equals == std::string::npos) continue;
            auto key = lowered.substr(0, equals);
            key.erase(std::remove_if(key.begin(), key.end(), [](unsigned char c) { return std::isspace(c); }), key.end());
            if (key != wanted) continue;
            auto value = lowered.substr(equals + 1);
            return value.find("false") == std::string::npos && value.find('0') == std::string::npos && value.find("no") == std::string::npos;
        }
        return fallback;
    }

    class DragonLinkMod final : public CppUserModBase
    {
        std::vector<LoadedFeature> m_features;

        void load_feature(const wchar_t* filename)
        {
            auto path = module_root() / "dlls" / filename;
            HMODULE module = LoadLibraryExW(path.c_str(), nullptr, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
            if (!module) { Output::send<LogLevel::Warning>(STR("[DragonLink] Could not load feature DLL {}.\n"), path.wstring()); return; }
            auto start = reinterpret_cast<StartMod>(GetProcAddress(module, "start_mod"));
            auto stop = reinterpret_cast<StopMod>(GetProcAddress(module, "uninstall_mod"));
            if (!start || !stop) { Output::send<LogLevel::Warning>(STR("[DragonLink] Feature DLL has no lifecycle exports: {}.\n"), path.wstring()); FreeLibrary(module); return; }
            auto* feature = start();
            if (!feature) { FreeLibrary(module); return; }
            feature->on_unreal_init();
            m_features.push_back({module, feature, stop});
            Output::send(STR("[DragonLink] Loaded feature {}.\n"), path.filename().wstring());
        }

      public:
        DragonLinkMod()
        {
            ModName = STR("DragonLink");
            ModAuthors = STR("Dragonwilds Sync");
            ModDescription = STR("Role-gated application bridge for Stacks/Weights, Connect, and Chat");
            ModVersion = STR("1.0.0");
        }

        ~DragonLinkMod() override
        {
            for (auto it = m_features.rbegin(); it != m_features.rend(); ++it) { it->stop(it->mod); FreeLibrary(it->module); }
        }

        void on_unreal_init() override
        {
            const bool server = server_process();
            if (feature_enabled("stacksweights", true)) load_feature(L"DragonLink-StacksWeights.dll");
            if (server && feature_enabled("chat", true)) load_feature(L"DragonLink-Chat.dll");
            if (!server && feature_enabled("connect", true)) load_feature(L"DragonLink-Connect.dll");
            Output::send(STR("[DragonLink] {} feature module(s) active in {} process.\n"), m_features.size(), server ? STR("server") : STR("client"));
        }
    };
}

extern "C"
{
    __declspec(dllexport) RC::CppUserModBase* start_mod() { return new DragonLinkMod(); }
    __declspec(dllexport) void uninstall_mod(RC::CppUserModBase* mod) { delete mod; }
}
