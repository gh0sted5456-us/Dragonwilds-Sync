-- DWSMDeathRelay — Dragonwilds Server Manager player-death relay
--
-- Detects player deaths server-side and appends one JSON line per death to
--   Pal/Saved/dwsm-deaths.jsonl
-- which the RuneScape Dragonwilds Server Manager app tails to log the death and route it to Discord.
--
-- Hook (one, low-frequency):
--   /Script/Pal.PalBattleManager:EventOnPlayerDeadCompletely(victim, PalDyingEndInfo)
--     fires once when a player has died (ALL death types — combat and environmental).
--     victim -> controller -> PlayerState.PlayerNamePrivate gives the name;
--     PalDyingEndInfo.DeadType gives the cause (EPalDeadType enum).
--
-- WHY NO KILLER ATTRIBUTION (removed in 2.6.1):
--   Earlier builds also hooked PalPlayerCharacter:OnDamagePlayer_Server — fired on EVERY
--   instance of a player taking damage — to remember the most recent attacker and name the
--   killer. That hook dereferenced the damage Attacker actor, which is null for
--   environmental damage and not-yet-valid for a just-spawned / just-logged-in player.
--   Reading a member off that invalid UObject raised a NATIVE EXCEPTION_ACCESS_VIOLATION
--   (reading address 0x1) deep inside UE4SS — and a native access violation is NOT catchable
--   by Lua pcall, so it took the whole dedicated server down (observed: two identical crashes
--   with ~2 players actively playing). Killer attribution isn't worth crashing the server, so
--   the damage hook is gone. Deaths and their cause are still reported.
--
-- HARDENING: every UObject we touch is checked with is_valid() (UE4SS's UObject:IsValid(),
--   which is safe to call on a null/invalid handle and returns false) BEFORE any property
--   read, so this hook can never repeat that native crash even on a malformed death event.
--
-- Requires UE4SS (experimental build) in the game's Binaries/Win64 layout.
--
-- Output path: the app's installer rewrites the placeholder below with an absolute path
-- to <install>/RSDragonwilds/Saved/dwsm-deaths.jsonl. If installed by hand (placeholder left as-is)
-- we fall back to relative candidates covering both known UE4SS layouts.

local CANDIDATES = {
    [[__DWSM_OUT_PATH__]],              -- absolute, rewritten by the app installer
    "../../../Saved/dwsm-deaths.jsonl", -- UE4SS 3.x layout (cwd = Win64/ue4ss)
    "../../Saved/dwsm-deaths.jsonl",    -- UE4SS 2.x layout (cwd = Win64)
    "./dwsm-deaths.jsonl",              -- last resort: next to UE4SS
}
local OUT_PATH = nil

local function resolve_out_path()
    if OUT_PATH then return OUT_PATH end
    for _, p in ipairs(CANDIDATES) do
        if p:sub(1, 2) ~= "__" then
            local f = io.open(p, "a")
            if f then f:close(); OUT_PATH = p
                print(string.format("[DWSMDeathRelay] writing deaths to: %s\n", p)); return OUT_PATH end
        end
    end
    return nil
end

local function esc(s)
    s = tostring(s or "")
    s = s:gsub("\\", "\\\\"):gsub('"', '\\"'):gsub("\n", "\\n"):gsub("\r", "\\r"):gsub("\t", "\\t")
    return s
end

local function now_ms() return math.floor(os.time() * 1000) end

-- Append one death record. Killer is always empty now (attribution removed); the app
-- treats an empty killer as an environmental / unattributed death.
local function append_death(victim, cause)
    local path = resolve_out_path()
    if not path then return end
    local ok, f = pcall(io.open, path, "a")
    if not ok or not f then OUT_PATH = nil; return end
    f:write(string.format(
        '{"victim":"%s","cause":"%s","killer":"","killerKind":"","at":%d}\n',
        esc(victim), esc(cause), now_ms()))
    f:close()
end

-- ToString-ish for FString/FName/objects.
local function to_str(v)
    if v == nil then return "" end
    local ok, s = pcall(function() return v:ToString() end)
    if ok and s then return s end
    return tostring(v)
end

local function unwrap(p)
    if type(p) == "userdata" and p.get then
        local ok, v = pcall(function() return p:get() end); if ok then return v end
    end
    return p
end

-- Safe validity gate for a UE4SS UObject handle. UObject:IsValid() is safe to call on a
-- null/stale handle (it checks the engine's object table, it does NOT dereference game
-- memory) and returns false — so this is the guard that prevents the native access
-- violation that a raw property read on an invalid object would cause.
local function is_valid(o)
    if type(o) ~= "userdata" then return false end
    local ok, v = pcall(function() return o:IsValid() end)
    return ok and v == true
end

-- A character's player name via its controller's PlayerState (engine APlayerState).
-- Every hop is validity-gated before the next dereference.
local function player_name_of(char)
    if not is_valid(char) then return "" end
    local nm = ""
    pcall(function()
        local ctrl = char:GetController()
        if not is_valid(ctrl) then return end
        local ps = ctrl.PlayerState
        if not is_valid(ps) then return end
        nm = to_str(ps.PlayerNamePrivate)
    end)
    return nm
end

-- Resolve an EPalDeadType value to its short name (e.g. 1 -> "Attack").
local function dead_type_name(v)
    local nm = nil
    pcall(function()
        local e = StaticFindObject("/Script/Pal.EPalDeadType")
        if e and e.GetNameByValue then nm = to_str(e:GetNameByValue(v)) end
    end)
    if nm and nm ~= "" then return (nm:gsub("^.*::", "")) end -- strip "EPalDeadType::"
    return tostring(v)
end

local function on_player_dead(self, victim_param, info_param)
    pcall(function()
        local victim = unwrap(victim_param)
        if not is_valid(victim) then return end
        local vname = player_name_of(victim)
        if vname == "" then return end

        local cause = ""
        pcall(function()
            local info = unwrap(info_param)
            if info then cause = dead_type_name(info.DeadType) end
        end)

        append_death(vname, cause)
        print(string.format("[DWSMDeathRelay] death: %s cause=%s\n", vname, cause))
    end)
end

-- The Pal class this lives on isn't in memory at mod-load, so register with retries.
local HOOKS = {
    { path = "/Script/Pal.PalBattleManager:EventOnPlayerDeadCompletely", fn = on_player_dead, done = false },
}

local function try_register()
    local remaining = 0
    for _, h in ipairs(HOOKS) do
        if not h.done then
            local ok = pcall(RegisterHook, h.path, h.fn)
            if ok then h.done = true; print("[DWSMDeathRelay] hooked " .. h.path .. "\n")
            else remaining = remaining + 1 end
        end
    end
    return remaining
end

-- Attempt now and again as the game finishes loading, until the hook is registered.
resolve_out_path()
if try_register() > 0 then
    for _, delay in ipairs({ 8000, 20000, 45000 }) do
        ExecuteWithDelay(delay, function() pcall(try_register) end)
    end
end
print("[DWSMDeathRelay] loaded (death-only, killer attribution disabled)\n")
