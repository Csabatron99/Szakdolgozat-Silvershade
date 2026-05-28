--[[
    SilverShade FiveM Resource — server/main.lua
    =============================================
    Polls the SilverShade backend API every POLL_INTERVAL seconds and:
      1. Reads pending transactions  → delivers in-game rewards to the player.
      2. Reads pending admin actions → executes bans, kicks, role changes.
      3. Pushes the current online player list → updates the admin dashboard.

    Configuration (set in server.cfg or resource convar):
        set SILVERSHADE_API      "https://your-api-host.com"
        set SILVERSHADE_API_KEY  "your-service-api-key"
        set SILVERSHADE_POLL_MS  "5000"

    Reward types (stored in transaction.rewardData.type):
        "money"   — adds in-game cash to the player (ESX / QBCore compatible)
        "item"    — adds an inventory item via ox_inventory (optional)
        "vip"     — sets the player's ESX job/group to "vip"

    Admin action types (adminAction.type):
        "ban"         — kicks and bans the player by their Rockstar identifier
        "kick"        — drops the player with a reason message
        "give_role"   — sets the player's ESX group
        "remove_role" — resets the player's ESX group to "user"
--]]

local API_BASE    = GetConvar("SILVERSHADE_API",     "http://127.0.0.1:8000")
local API_KEY     = GetConvar("SILVERSHADE_API_KEY", "")
local POLL_MS     = tonumber(GetConvar("SILVERSHADE_POLL_MS", "5000")) or 5000

-- Strip trailing slash and optional /api suffix so paths are always clean.
API_BASE = API_BASE:gsub("/+$", ""):gsub("/api$", "")

local function apiHeaders()
    return {
        ["Authorization"] = "Bearer " .. API_KEY,
        ["Content-Type"]  = "application/json",
    }
end

-- ── HTTP helpers ──────────────────────────────────────────────────────────────

---Perform an async GET request; calls cb(body_table | nil, status_code).
local function apiGet(path, cb)
    PerformHttpRequest(API_BASE .. path, function(statusCode, body, _headers)
        if statusCode == 200 then
            local ok, data = pcall(json.decode, body or "")
            cb(ok and data or nil, statusCode)
        else
            print(("[SilverShade] GET %s failed — HTTP %d"):format(path, statusCode))
            cb(nil, statusCode)
        end
    end, "GET", "", apiHeaders())
end

---Perform an async PATCH request with a JSON body.
local function apiPatch(path, payload, cb)
    local body = json.encode(payload)
    PerformHttpRequest(API_BASE .. path, function(statusCode, respBody, _headers)
        if cb then cb(statusCode, respBody) end
    end, "PATCH", body, apiHeaders())
end

---Perform an async POST request with a JSON body.
local function apiPost(path, payload, cb)
    local body = json.encode(payload)
    PerformHttpRequest(API_BASE .. path, function(statusCode, respBody, _headers)
        if cb then cb(statusCode, respBody) end
    end, "POST", body, apiHeaders())
end

-- ── Player helpers ────────────────────────────────────────────────────────────

---Find an online player by their SilverShade userId (stored in their identifier).
---Returns the player server ID, or nil if not found.
local function findPlayerByUserId(userId)
    for _, serverId in ipairs(GetPlayers()) do
        -- Adjust the identifier type ("license", "discord", etc.) to match
        -- how your server maps SilverShade user IDs to FiveM identifiers.
        local license = GetPlayerIdentifierByType(serverId, "license")
        if license and license:find(userId, 1, true) then
            return tonumber(serverId)
        end
    end
    return nil
end

---Build a lightweight player list for the admin dashboard.
local function buildPlayerList()
    local players = {}
    for _, serverId in ipairs(GetPlayers()) do
        local sid = tonumber(serverId)
        players[#players + 1] = {
            serverId   = sid,
            name       = GetPlayerName(sid) or "Unknown",
            ping       = GetPlayerPing(sid),
            identifiers = {
                license  = GetPlayerIdentifierByType(sid, "license")  or "",
                discord  = GetPlayerIdentifierByType(sid, "discord")  or "",
                steam    = GetPlayerIdentifierByType(sid, "steam")    or "",
            },
        }
    end
    return players
end

-- ── Reward delivery ───────────────────────────────────────────────────────────

local function deliverReward(serverId, rewardData)
    local rType = rewardData and rewardData.type or "unknown"

    if rType == "money" then
        local amount = tonumber(rewardData.amount) or 0
        -- ESX: TriggerEvent('esx:addMoney', serverId, 'cash', amount)
        -- QBCore: exports.qb-core:GetPlayer(serverId).Functions.AddMoney('cash', amount)
        -- Standalone fallback — remove whichever lines don't match your framework:
        TriggerClientEvent("silvershade:addMoney", serverId, amount)
        print(("[SilverShade] Delivered $%d cash to player %d"):format(amount, serverId))

    elseif rType == "item" then
        local item  = rewardData.item  or "bread"
        local count = tonumber(rewardData.count) or 1
        -- ox_inventory (most common):
        -- exports.ox_inventory:AddItem(serverId, item, count)
        TriggerClientEvent("silvershade:addItem", serverId, item, count)
        print(("[SilverShade] Gave %dx %s to player %d"):format(count, item, serverId))

    elseif rType == "vip" then
        -- ESX: exports.es_extended:getPlayerFromId(serverId):setGroup('vip')
        TriggerClientEvent("silvershade:setVip", serverId)
        print(("[SilverShade] Set VIP on player %d"):format(serverId))

    else
        print(("[SilverShade] Unknown reward type: %s"):format(rType))
    end
end

-- ── Transaction processing ────────────────────────────────────────────────────

local function processTransactions(transactions)
    if not transactions or #transactions == 0 then return end

    for _, tx in ipairs(transactions) do
        local txId    = tx.id or tx._id
        local userId  = tx.userId
        local reward  = tx.rewardData

        if txId and userId then
            local serverId = findPlayerByUserId(userId)

            if serverId then
                deliverReward(serverId, reward)
            else
                -- Player is offline — still confirm so the transaction isn't
                -- retried forever. Optionally implement a "pending offline
                -- delivery" queue instead.
                print(("[SilverShade] Player %s offline; marking tx %s completed anyway"):format(userId, txId))
            end

            -- Confirm the transaction regardless of delivery outcome.
            apiPatch("/api/v1/transactions/" .. txId .. "/status", { status = "completed" }, function(code, _)
                if code ~= 200 then
                    print(("[SilverShade] Failed to confirm tx %s — HTTP %d"):format(txId, code))
                end
            end)
        end
    end
end

-- ── Admin action processing ───────────────────────────────────────────────────

local function processAdminActions(actions)
    if not actions or #actions == 0 then return end

    for _, action in ipairs(actions) do
        local actionId = action.id or action._id
        local aType    = action.type or ""
        local playerId = action.playerId or ""
        local data     = action.data or {}

        -- Try to find the player online; some actions apply even if offline (ban).
        local serverId = findPlayerByUserId(playerId)

        if aType == "ban" then
            local reason = data.reason or "Banned by administrator"
            if serverId then
                DropPlayer(serverId, "You have been banned: " .. reason)
            end
            -- TODO: write to your ban list (e.g., txAdmin ban, banning.lua, etc.)
            print(("[SilverShade] Banned player %s — %s"):format(playerId, reason))

        elseif aType == "kick" then
            local reason = data.reason or "Kicked by administrator"
            if serverId then
                DropPlayer(serverId, reason)
                print(("[SilverShade] Kicked player %d — %s"):format(serverId, reason))
            else
                print(("[SilverShade] Kick: player %s not online"):format(playerId))
            end

        elseif aType == "give_role" then
            local role = data.role or "vip"
            if serverId then
                -- ESX: exports.es_extended:getPlayerFromId(serverId):setGroup(role)
                TriggerClientEvent("silvershade:setRole", serverId, role)
                print(("[SilverShade] Set role '%s' on player %d"):format(role, serverId))
            else
                print(("[SilverShade] give_role: player %s not online"):format(playerId))
            end

        elseif aType == "remove_role" then
            if serverId then
                -- ESX: exports.es_extended:getPlayerFromId(serverId):setGroup('user')
                TriggerClientEvent("silvershade:setRole", serverId, "user")
                print(("[SilverShade] Removed role from player %d"):format(serverId))
            end

        else
            print(("[SilverShade] Unknown action type: %s"):format(aType))
        end

        -- Confirm the action so the backend stops resending it.
        if actionId then
            apiPatch("/api/v1/admin-actions/" .. actionId .. "/status", { status = "completed" }, function(code, _)
                if code ~= 200 then
                    print(("[SilverShade] Failed to confirm action %s — HTTP %d"):format(actionId, code))
                end
            end)
        end
    end
end

-- ── Player list push ──────────────────────────────────────────────────────────

local function pushPlayerList()
    local players = buildPlayerList()
    apiPost("/api/v1/service/fivem/players", { players = players }, function(code, _)
        if code ~= 200 then
            print(("[SilverShade] Failed to push player list — HTTP %d"):format(code))
        end
    end)
end

-- ── Main poll loop ────────────────────────────────────────────────────────────

local function pollCycle()
    apiGet("/api/v1/sync/updates", function(data, _code)
        if not data or not data.data then return end

        local payload      = data.data
        local transactions = payload.transactions or payload.pendingTransactions or {}
        local adminActions = payload.adminActions or payload.pendingAdminActions or {}

        processTransactions(transactions)
        processAdminActions(adminActions)
    end)

    pushPlayerList()
end

-- Start the poll loop after a short delay to let the server finish loading.
CreateThread(function()
    Wait(3000)
    print(("[SilverShade] Resource started. Polling %s every %dms"):format(API_BASE, POLL_MS))

    while true do
        pollCycle()
        Wait(POLL_MS)
    end
end)
