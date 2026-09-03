-- DragonConnect
-- Dragonwilds Sync client Core: verified one-time Direct Connect handoff.

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
local world_type = string.lower(tostring(config.world_type or "normal"))
local auto_navigate = config.auto_navigate ~= false
local auto_submit = config.auto_submit ~= false

if not enabled or address == "" then
    print("[DragonConnect] No active World connection is configured.\n")
    return
end

local hydrated = setmetatable({}, { __mode = "k" })
local clicked = setmetatable({}, { __mode = "k" })
local address_ready = false
local password_ready = password == ""
local type_ready = world_type == "normal"
local submit_complete = false
local navigation_attempted = false

local function lower(value)
    return string.lower(tostring(value or ""))
end

local function full_name(object)
    local ok, value = pcall(function() return object:GetFullName() end)
    return ok and tostring(value or "") or ""
end

local function endpoint_parts(value)
    local raw = tostring(value or "")
    local bracket_host, bracket_port = string.match(raw, "^%[([^%]]+)%]:(%d+)$")
    if bracket_host then return bracket_host, bracket_port end
    local host, port = string.match(raw, "^([^:]+):(%d+)$")
    if host then return host, port end
    return raw, "7777"
end

local endpoint_host, endpoint_port = endpoint_parts(address)

local function direct_context(name)
    return string.find(name, "direct", 1, true)
        or string.find(name, "serverbrowser", 1, true)
        or string.find(name, "server_browser", 1, true)
        or string.find(name, "server browser", 1, true)
        or string.find(name, "joinserver", 1, true)
end

local function classify_field(widget)
    local name = lower(full_name(widget))
    if name == "" or string.find(name, "default__", 1, true) then return nil end
    if not direct_context(name) and not string.find(name, "connect", 1, true) and not string.find(name, "join", 1, true) then
        return nil
    end
    if string.find(name, "password", 1, true)
        or string.find(name, "passcode", 1, true)
        or string.find(name, "worldpass", 1, true) then
        return "password"
    end
    if string.find(name, "port", 1, true) and not string.find(name, "viewport", 1, true) then
        return "port"
    end
    if string.find(name, "ipaddress", 1, true)
        or string.find(name, "serveraddress", 1, true)
        or string.find(name, "serverip", 1, true)
        or string.find(name, "address", 1, true)
        or string.find(name, "endpoint", 1, true) then
        return "address"
    end
    return nil
end

local function collect_fields()
    local rows = {}
    for _, class_name in ipairs({ "EditableTextBox", "EditableText" }) do
        local ok, widgets = pcall(FindAllOf, class_name)
        if ok and widgets then
            for _, widget in pairs(widgets) do
                local field = classify_field(widget)
                if field then table.insert(rows, { widget = widget, field = field }) end
            end
        end
    end
    return rows
end

local function hydrate_fields()
    local rows = collect_fields()
    local has_port = false
    for _, row in ipairs(rows) do if row.field == "port" then has_port = true break end end

    for _, row in ipairs(rows) do
        local widget, field = row.widget, row.field
        if not hydrated[widget] then
            local value = ""
            if field == "address" then value = has_port and endpoint_host or address end
            if field == "port" then value = endpoint_port end
            if field == "password" then value = password end
            local ok = pcall(function()
                if not widget:IsValid() then return end
                widget:SetText(FText(value))
                hydrated[widget] = true
            end)
            if ok then
                if field == "address" then address_ready = true end
                if field == "password" then password_ready = true end
            end
        end
    end
    return #rows > 0
end

local function button_descriptor(button)
    local parts = { full_name(button) }
    pcall(function()
        local delegate = button.OnClicked
        local bindings = delegate and delegate:GetBindings() or nil
        if bindings then
            for _, binding in ipairs(bindings) do
                table.insert(parts, tostring(binding.FunctionName or ""))
                if binding.Object then table.insert(parts, full_name(binding.Object)) end
            end
        end
    end)
    return lower(table.concat(parts, " | "))
end

local function safe_button(button, predicate)
    if clicked[button] then return false end
    local name = button_descriptor(button)
    if name == "" or string.find(name, "default__", 1, true) then return false end
    if string.find(name, "back", 1, true) or string.find(name, "cancel", 1, true)
        or string.find(name, "close", 1, true) or string.find(name, "delete", 1, true)
        or string.find(name, "disconnect", 1, true) then return false end
    return predicate(name)
end

local function unique_button(predicate)
    local matches = {}
    local ok, buttons = pcall(FindAllOf, "Button")
    if not ok or not buttons then return nil end
    for _, button in pairs(buttons) do
        local valid = false
        pcall(function() valid = button:IsValid() end)
        if valid and safe_button(button, predicate) then table.insert(matches, button) end
    end
    if #matches == 1 then return matches[1] end
    if #matches > 1 then
        print(string.format("[DragonConnect] Refusing ambiguous automatic click (%d candidates).\n", #matches))
    end
    return nil
end

local function broadcast_click(button, label)
    if not button then return false end
    local ok, error_text = pcall(function()
        button.OnClicked:Broadcast()
        clicked[button] = true
    end)
    if ok then
        print(string.format("[DragonConnect] Activated %s control.\n", label))
        return true
    end
    print(string.format("[DragonConnect] Could not activate %s control: %s\n", label, tostring(error_text)))
    return false
end

local function play_button(name)
    if string.find(name, "player", 1, true) then return false end
    local action = string.find(name, "playbutton", 1, true)
        or string.find(name, "button_play", 1, true)
        or string.find(name, "play_button", 1, true)
        or string.find(name, ".play", 1, true)
    local menu = string.find(name, "mainmenu", 1, true)
        or string.find(name, "main_menu", 1, true)
        or string.find(name, "frontend", 1, true)
        or string.find(name, "front_end", 1, true)
    return action and menu
end

local function direct_tab_button(name)
    if not string.find(name, "direct", 1, true) then return false end
    if string.find(name, "connect", 1, true) and not string.find(name, "tab", 1, true) then return false end
    return string.find(name, "tab", 1, true)
        or string.find(name, "filter", 1, true)
        or string.find(name, "browser", 1, true)
        or string.find(name, "mode", 1, true)
end

local function connect_button(name)
    if not direct_context(name) then return false end
    if string.find(name, "tab", 1, true) or string.find(name, "filter", 1, true)
        or string.find(name, "mode", 1, true) then return false end
    return string.find(name, "connectbutton", 1, true)
        or string.find(name, "button_connect", 1, true)
        or string.find(name, "joinbutton", 1, true)
        or string.find(name, "button_join", 1, true)
        or string.find(name, "enterworld", 1, true)
        or string.find(name, "enter_world", 1, true)
end

local function apply_world_type()
    if type_ready then return true end
    local target = world_type == "creative" and "creative" or "custom"

    local combo_matches = {}
    local ok, combos = pcall(FindAllOf, "ComboBoxString")
    if ok and combos then
        for _, combo in pairs(combos) do
            local name = lower(full_name(combo))
            if direct_context(name) and (string.find(name, "type", 1, true) or string.find(name, "mode", 1, true)) then
                table.insert(combo_matches, combo)
            end
        end
    end
    if #combo_matches == 1 then
        local label = target == "creative" and "Creative" or "Custom"
        local changed = pcall(function() combo_matches[1]:SetSelectedOption(label) end)
        if changed then
            type_ready = true
            print(string.format("[DragonConnect] Selected %s World type.\n", label))
            return true
        end
    end

    local button = unique_button(function(name)
        return direct_context(name) and string.find(name, target, 1, true)
            and (string.find(name, "type", 1, true) or string.find(name, "mode", 1, true) or string.find(name, "button", 1, true))
    end)
    if button and broadcast_click(button, target .. " World type") then
        type_ready = true
        return true
    end
    return false
end

local function scan()
    if submit_complete then return end

    local fields_visible = hydrate_fields()
    if fields_visible and address_ready and password_ready then
        apply_world_type()
        if auto_submit and type_ready then
            local connect = unique_button(connect_button)
            if connect and broadcast_click(connect, "Direct Connect") then
                submit_complete = true
                print("[DragonConnect] Verified Direct Connect handoff submitted.\n")
            end
        end
        return
    end

    if not auto_navigate then return end

    local direct = unique_button(direct_tab_button)
    if direct and broadcast_click(direct, "Direct tab") then
        navigation_attempted = true
        return
    end

    if not navigation_attempted then
        local play = unique_button(play_button)
        if play and broadcast_click(play, "Play") then
            navigation_attempted = true
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

-- UI construction is asynchronous. Keep this retry window bounded: enough time
-- for main-menu -> Play -> Direct navigation and field creation, but no permanent
-- polling loop or repeated clicks after the handoff has completed.
for _, delay in ipairs({ 0, 100, 300, 750, 1500, 2500, 4000, 6500, 9000, 12000 }) do later(delay) end

pcall(function()
    RegisterHook("/Script/UMG.UserWidget:Construct", function()
        later(0)
        later(120)
        later(350)
        later(800)
    end)
end)

print(string.format("[DragonConnect] Direct Connect handoff active for %s (%s).\n", address, world_type))
