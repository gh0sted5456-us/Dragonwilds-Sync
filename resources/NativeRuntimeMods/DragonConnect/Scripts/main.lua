-- DragonConnect
-- Dragonwilds Sync client Core: one-time Direct Connect credential hydration.

local config = {}
do
    local ok, loaded = pcall(require, "config")
    if ok and type(loaded) == "table" then
        config = loaded
    end
end

local enabled = config.enabled == true
local address = tostring(config.address or config.ip or "")
local password = tostring(config.password or "")

if not enabled or address == "" then
    print("[DragonConnect] No active World connection is configured.\n")
    return
end

local hydrated = setmetatable({}, { __mode = "k" })

local function lower(value)
    return string.lower(tostring(value or ""))
end

local function classify(widget)
    local ok, full_name = pcall(function() return widget:GetFullName() end)
    if not ok then return nil end
    local name = lower(full_name)
    if string.find(name, "default__", 1, true) then return nil end
    if not string.find(name, "editabletext", 1, true) and not string.find(name, "editabletextbox", 1, true) then
        return nil
    end

    local connect_surface = string.find(name, "direct", 1, true)
        or string.find(name, "connect", 1, true)
        or string.find(name, "join", 1, true)
        or string.find(name, "server", 1, true)
    if not connect_surface then return nil end

    if string.find(name, "ipaddress", 1, true)
        or string.find(name, "serveraddress", 1, true)
        or string.find(name, "serverip", 1, true)
        or string.find(name, "address", 1, true)
        or string.find(name, "endpoint", 1, true) then
        return "address"
    end
    if string.find(name, "password", 1, true)
        or string.find(name, "passcode", 1, true)
        or string.find(name, "worldpass", 1, true) then
        return "password"
    end
    return nil
end

local function hydrate(widget)
    if hydrated[widget] then return false end
    local field = classify(widget)
    if not field then return false end
    local value = field == "address" and address or password
    if value == "" and field == "password" then
        hydrated[widget] = true
        return false
    end

    local ok = pcall(function()
        if not widget:IsValid() then return end
        widget:SetText(FText(value))
        hydrated[widget] = true
    end)
    return ok
end

local function scan()
    for _, class_name in ipairs({ "EditableTextBox", "EditableText" }) do
        local ok, widgets = pcall(FindAllOf, class_name)
        if ok and widgets then
            for _, widget in pairs(widgets) do
                hydrate(widget)
            end
        end
    end
end

local function later(delay_ms)
    if type(ExecuteInGameThreadWithDelay) == "function" then
        ExecuteInGameThreadWithDelay(delay_ms, scan)
    elseif type(ExecuteWithDelay) == "function" then
        ExecuteWithDelay(delay_ms, scan)
    end
end

-- The Direct Connect widget can build its editable fields a few frames after
-- the parent UserWidget. A short bounded retry sequence handles that without a
-- permanent polling loop and never overwrites the same widget twice.
for _, delay in ipairs({ 0, 100, 300, 750, 1500 }) do later(delay) end

pcall(function()
    RegisterHook("/Script/UMG.UserWidget:Construct", function()
        later(0)
        later(120)
        later(350)
    end)
end)

print("[DragonConnect] Direct Connect handoff active.\n")
