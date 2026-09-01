#define NOMINMAX
#include <Windows.h>

#include <algorithm>
#include <chrono>
#include <cctype>
#include <cstdio>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <string>
#include <unordered_map>
#include <vector>

#include <DynamicOutput/DynamicOutput.hpp>
#include <Mod/CppUserModBase.hpp>
#include <Unreal/CoreUObject/UObject/UnrealType.hpp>
#include <Unreal/Hooks/Hooks.hpp>
#include <Unreal/UObjectGlobals.hpp>
#include <UEngine.hpp>

namespace
{
    using namespace RC;
    using namespace RC::Unreal;

    struct Config
    {
        bool enabled{true};
        double proximity_threshold{1200.0};
        double exit_threshold{1350.0};
        double magnet_range{800.0};
        double state_delay_seconds{10.0};
        double refresh_seconds{0.35};
        bool debug{false};
    };

    struct Vector { double x{}, y{}, z{}; };
    struct Player { UObject* actor{}; UObject* magnet{}; std::string id; Vector location{}; bool crowded{}; };
    struct CrowdState { bool crowded{}; bool initialized{}; std::chrono::steady_clock::time_point pending_since{}; };

    std::filesystem::path mod_root()
    {
        HMODULE module{};
        GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           reinterpret_cast<LPCWSTR>(&mod_root), &module);
        wchar_t path[MAX_PATH]{};
        GetModuleFileNameW(module, path, MAX_PATH);
        return std::filesystem::path(path).parent_path().parent_path();
    }

    std::string trim(std::string value)
    {
        auto blank=[](unsigned char c){return std::isspace(c)!=0;};
        value.erase(value.begin(),std::find_if(value.begin(),value.end(),[&](char c){return !blank(c);}));
        value.erase(std::find_if(value.rbegin(),value.rend(),[&](char c){return !blank(c);}).base(),value.end());
        return value;
    }

    Config load_config()
    {
        Config result;
        std::ifstream input(mod_root() / "ProximityLoot.ini");
        bool section=false;
        for(std::string line;std::getline(input,line);)
        {
            auto lower=line;std::transform(lower.begin(),lower.end(),lower.begin(),[](unsigned char c){return static_cast<char>(std::tolower(c));});
            if(lower.find('[')!=std::string::npos){section=lower.find("[proximityloot]")!=std::string::npos;continue;}
            if(!section)continue;auto equals=lower.find('=');if(equals==std::string::npos)continue;
            auto key=trim(lower.substr(0,equals));auto value=trim(lower.substr(equals+1));
            try {
                if(key=="enabled")result.enabled=value!="false"&&value!="0"&&value!="no";
                else if(key=="proximitythreshold")result.proximity_threshold=std::stod(value);
                else if(key=="proximityexitthreshold")result.exit_threshold=std::stod(value);
                else if(key=="enhancedmagnetrange")result.magnet_range=std::stod(value);
                else if(key=="statedelayseconds")result.state_delay_seconds=std::stod(value);
                else if(key=="refreshseconds")result.refresh_seconds=std::stod(value);
                else if(key=="debug")result.debug=value=="true"||value=="1"||value=="yes";
            } catch (...) { Output::send<LogLevel::Warning>(STR("[DragonLink-ProximityLoot] Ignored invalid config value.\n")); }
        }
        result.proximity_threshold=std::clamp(result.proximity_threshold,0.0,100000.0);
        result.exit_threshold=std::max(result.proximity_threshold,std::clamp(result.exit_threshold,0.0,100000.0));
        result.magnet_range=std::clamp(result.magnet_range,0.0,100000.0);
        result.state_delay_seconds=std::clamp(result.state_delay_seconds,0.0,120.0);
        result.refresh_seconds=std::clamp(result.refresh_seconds,0.1,5.0);
        return result;
    }

    UObject* object_property(UObject* owner,const wchar_t* name)
    {
        if(!owner||!UObject::IsReal(owner))return nullptr;
        auto* property=owner->GetPropertyByNameInChain(name);if(!property)return nullptr;
        auto* result=*static_cast<UObject**>(property->ContainerPtrToValuePtr<void>(owner));
        return result&&UObject::IsReal(result)?result:nullptr;
    }

    void import_property(UObject* owner,const wchar_t* name,const std::wstring& value)
    {
        if(!owner||!UObject::IsReal(owner))return;auto* property=owner->GetPropertyByNameInChain(name);if(!property)return;
        property->ImportText(value.c_str(),property->ContainerPtrToValuePtr<void>(owner),0,owner,nullptr);
    }

    bool location(UObject* actor,Vector& value)
    {
        static auto* function=UObjectGlobals::StaticFindObject<UFunction*>(nullptr,nullptr,STR("/Script/Engine.Actor:K2_GetActorLocation"));
        if(!function||!actor)return false;
        std::vector<unsigned char> params(function->GetParmsSize());actor->ProcessEvent(function,params.data());
        auto* result=function->GetPropertyByNameInChain(STR("ReturnValue"));if(!result)return false;
        FString text{};void* data=result->ContainerPtrToValuePtr<void>(params.data());result->ExportTextItem(text,data,data,actor,0);
        auto raw=to_string(*text);return std::sscanf(raw.c_str(),"(X=%lf,Y=%lf,Z=%lf)",&value.x,&value.y,&value.z)==3;
    }

    void set_range(UObject* magnet,double range)
    {
        import_property(magnet,L"MagnetRange",std::to_wstring(range));
        const auto flag=range>0.0?L"True":L"False";
        import_property(magnet,L"bAllowAutoMagnetization",flag);
        import_property(magnet,L"bAutoMagnetizationEnabled",flag);
    }

    class DragonLinkProximityLootMod final : public CppUserModBase
    {
        Config m_config{};
        std::filesystem::file_time_type m_config_mtime{};
        std::unordered_map<std::string,CrowdState> m_states;
        Hook::GlobalCallbackId m_tick{};
        std::chrono::steady_clock::time_point m_last_tick{};
        std::chrono::steady_clock::time_point m_last_config{};

        void reload_if_changed()
        {
            auto path=mod_root()/"ProximityLoot.ini";std::error_code error;auto changed=std::filesystem::last_write_time(path,error);
            if(error||changed==m_config_mtime)return;m_config_mtime=changed;m_config=load_config();
            Output::send(STR("[DragonLink-ProximityLoot] Hot-reloaded: enter {:.0f}, exit {:.0f}, magnet {:.0f}.\n"),m_config.proximity_threshold,m_config.exit_threshold,m_config.magnet_range);
        }

        void update()
        {
            auto now=std::chrono::steady_clock::now();
            if(now-m_last_config>=std::chrono::seconds(1)){m_last_config=now;reload_if_changed();}
            if(!m_config.enabled||std::chrono::duration<double>(now-m_last_tick).count()<m_config.refresh_seconds)return;m_last_tick=now;
            std::vector<UObject*> objects;UObjectGlobals::FindAllOf(STR("DominionPlayerCharacter"),objects);std::vector<Player> players;
            for(auto* actor:objects){if(!actor||!UObject::IsReal(actor))continue;auto* magnet=object_property(actor,L"BP_Components_ItemMagnet");if(!magnet)magnet=object_property(actor,L"BP_Components_ItemMagnet_GEN_VARIABLE");Vector point{};if(!magnet||!location(actor,point))continue;players.push_back({actor,magnet,to_string(actor->GetFullName()),point,false});}
            for(size_t i=0;i<players.size();++i)for(size_t j=i+1;j<players.size();++j){auto dx=players[i].location.x-players[j].location.x,dy=players[i].location.y-players[j].location.y,dz=players[i].location.z-players[j].location.z;auto distance=dx*dx+dy*dy+dz*dz;auto left=m_states[players[i].id].crowded?m_config.exit_threshold:m_config.proximity_threshold;auto right=m_states[players[j].id].crowded?m_config.exit_threshold:m_config.proximity_threshold;if(distance<=left*left)players[i].crowded=true;if(distance<=right*right)players[j].crowded=true;}
            std::unordered_map<std::string,bool> live;
            for(auto& player:players){live[player.id]=true;auto& state=m_states[player.id];if(!state.initialized){state.initialized=true;state.crowded=player.crowded;}else if(state.crowded!=player.crowded){if(state.pending_since.time_since_epoch().count()==0)state.pending_since=now;else if(std::chrono::duration<double>(now-state.pending_since).count()>=m_config.state_delay_seconds){state.crowded=player.crowded;state.pending_since={};}}else state.pending_since={};set_range(player.magnet,state.crowded?0.0:m_config.magnet_range);}
            for(auto it=m_states.begin();it!=m_states.end();)if(!live.contains(it->first))it=m_states.erase(it);else ++it;
        }

      public:
        DragonLinkProximityLootMod(){ModName=STR("DragonLink-ProximityLoot");ModAuthors=STR("Dragonwilds Sync / ProximityLoot");ModDescription=STR("Hot-reloadable proximity loot magnet control");ModVersion=STR("1.0.0");}
        ~DragonLinkProximityLootMod() override{if(m_tick)Hook::UnregisterCallback(m_tick);}
        void on_unreal_init() override{m_config=load_config();std::error_code error;m_config_mtime=std::filesystem::last_write_time(mod_root()/"ProximityLoot.ini",error);m_tick=Hook::RegisterEngineTickPreCallback([this](auto&,UEngine*,float,bool){update();},{false,false,STR("DragonLink-ProximityLoot"),STR("ProximityUpdate")});Output::send(STR("[DragonLink-ProximityLoot] Standalone mod active; ProximityLoot.ini hot reload is enabled.\n"));}
    };
}

extern "C"
{
    __declspec(dllexport) RC::CppUserModBase* start_mod(){return new DragonLinkProximityLootMod();}
    __declspec(dllexport) void uninstall_mod(RC::CppUserModBase* mod){delete mod;}
}
