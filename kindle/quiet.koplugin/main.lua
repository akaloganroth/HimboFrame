--[[--
Quiet Screens for KOReader.

Shows the picture the Quiet Screens add-on hands out and sends taps on its
buttons back. The add-on decides everything: which picture, how soon to ask
again, and where the buttons are. This plugin never needs to change when the
screens do.

Setup: put the add-on's address in server.txt (one line). If the add-on has a
kindle_token set, put the same value in token.txt.

Start it from Tools > Quiet Screens. Hold anywhere on the screen to leave.

Written against the same KOReader calls TRMNL's plugin uses
(github.com/usetrmnl/trmnl-koreader).
]]

local DataStorage = require("datastorage")
local Device = require("device")
local Geom = require("ui/geometry")
local GestureRange = require("ui/gesturerange")
local ImageWidget = require("ui/widget/imagewidget")
local InfoMessage = require("ui/widget/infomessage")
local InputContainer = require("ui/widget/container/inputcontainer")
local NetworkMgr = require("ui/network/manager")
local RenderImage = require("ui/renderimage")
local UIManager = require("ui/uimanager")
local WidgetContainer = require("ui/widget/container/widgetcontainer")
local lfs = require("libs/libkoreader-lfs")
local logger = require("logger")
local _ = require("gettext")
local Screen = Device.screen

local RETRY_SECONDS = 60          -- after a failed fetch
local AFTER_TAP_SECONDS = 2       -- give the Mac a moment to act and redraw

local Quiet = WidgetContainer:extend {
    name = "quiet",
    is_doc_only = false,
    running = false,
    buttons = nil,
    last_filename = nil,
}

local function plugin_dir()
    local source = debug.getinfo(1, "S").source:match("^@(.+)$")
    return source and source:match("(.*/)") or "./"
end

local function first_line(path)
    local file = io.open(path, "r")
    if not file then return nil end
    local line = file:read("*l")
    file:close()
    if line then line = line:gsub("%s+$", "") end
    return (line and line ~= "") and line or nil
end

function Quiet:init()
    self.server = (first_line(plugin_dir() .. "server.txt") or ""):gsub("/+$", "")
    self.token = first_line(plugin_dir() .. "token.txt")
    self.folder = DataStorage:getDataDir() .. "/quiet"
    lfs.mkdir(self.folder)
    self.refresh_task = function() self:fetch() end
    self.ui.menu:registerToMainMenu(self)
end

function Quiet:addToMainMenu(menu_items)
    menu_items.quiet = {
        text = _("Quiet Screens"),
        sorting_hint = "tools",
        callback = function() self:start() end,
    }
end

function Quiet:start()
    if self.server == "" then
        UIManager:show(InfoMessage:new { text = _("Quiet Screens: put the add-on's address in server.txt") })
        return
    end
    self.running = true
    -- Keep the Kindle from dozing between fetches, where KOReader supports it.
    pcall(function() UIManager:preventStandby() end)
    self:fetch()
end

function Quiet:stop()
    self.running = false
    UIManager:unschedule(self.refresh_task)
    pcall(function() UIManager:allowStandby() end)
    if self.image_widget then
        UIManager:close(self.image_widget)
        self.image_widget = nil
    end
end

function Quiet:schedule(seconds)
    UIManager:unschedule(self.refresh_task)
    if self.running then
        UIManager:scheduleIn(seconds, self.refresh_task)
    end
end

--- One HTTP request. Returns the body, or nil and a reason.
function Quiet:request(url, body, file)
    local http = require("socket.http")
    local https = require("ssl.https")
    local ltn12 = require("ltn12")
    local socketutil = require("socketutil")
    local chunks = {}
    local request = {
        url = url,
        method = body and "POST" or "GET",
        headers = {
            ["User-Agent"] = "quiet-koreader",
            ["X-Quiet-Token"] = self.token,
            -- The screen's shape as it is held now, so the picture can match.
            ["png-width"] = tostring(Screen:getWidth()),
            ["png-height"] = tostring(Screen:getHeight()),
        },
        sink = file and socketutil.file_sink(file) or socketutil.table_sink(chunks),
        protocol = "any",
        options = { "all", "no_sslv2", "no_sslv3" },
        verify = "none",   -- Kindles carry an outdated certificate store
    }
    if body then
        request.headers["Content-Type"] = "application/json"
        request.headers["Content-Length"] = tostring(#body)
        request.source = ltn12.source.string(body)
    end
    local httpx = url:match("^https://") and https or http
    socketutil:set_timeout(socketutil.LARGE_BLOCK_TIMEOUT, socketutil.LARGE_TOTAL_TIMEOUT)
    local ok, status = httpx.request(request)
    socketutil:reset_timeout()
    if ok ~= 1 then return nil, tostring(status) end
    if status ~= 200 then return nil, "HTTP " .. tostring(status) end
    return table.concat(chunks)
end

function Quiet:fetch()
    if not self.running then return end
    NetworkMgr:runWhenConnected(function()
        local ok, err = pcall(function() self:fetchNow() end)
        if not ok then
            logger.err("Quiet: fetch failed:", err)
            self:schedule(RETRY_SECONDS)
        end
    end)
end

function Quiet:fetchNow()
    local JSON = require("json")
    local body, reason = self:request(self.server .. "/api/display")
    if not body then
        logger.warn("Quiet: no answer from the add-on:", reason)
        return self:schedule(RETRY_SECONDS)
    end
    local parsed, response = pcall(JSON.decode, body)
    if not parsed or type(response) ~= "table" or not response.image_url then
        logger.warn("Quiet: unexpected answer from the add-on")
        return self:schedule(RETRY_SECONDS)
    end

    self.buttons = type(response.buttons) == "table" and response.buttons or {}

    local filename = tostring(response.filename or "screen"):gsub("[^%w%-_]", "_") .. ".png"
    local path = self.folder .. "/" .. filename
    if filename ~= self.last_filename or not self.image_widget then
        if filename ~= self.last_filename then
            local file = io.open(path, "wb")
            if not file then return self:schedule(RETRY_SECONDS) end
            local got = self:request(response.image_url, nil, file)
            if not got then
                os.remove(path)
                return self:schedule(RETRY_SECONDS)
            end
            for name in lfs.dir(self.folder) do
                if name:match("%.png$") and name ~= filename and name ~= "sleep.png" then
                    os.remove(self.folder .. "/" .. name)
                end
            end
            -- Keep the last screen that did not come from the Mac (the TRMNL
            -- screen) at a fixed path, so it can be used as the sleep screen.
            if not filename:match("^mac%-") then
                local from, to = io.open(path, "rb"), io.open(self.folder .. "/sleep.png", "wb")
                if from and to then to:write(from:read("*a")) end
                if from then from:close() end
                if to then to:close() end
            end
            self.last_filename = filename
        end
        self:show(path)
    end
    self:schedule(tonumber(response.refresh_rate) or 300)
end

function Quiet:show(path)
    local width, height = Screen:getWidth(), Screen:getHeight()
    local bitmap = RenderImage:renderImageFile(path, false, width, height)
    if not bitmap then
        logger.warn("Quiet: could not draw", path)
        return
    end
    if self.image_widget then
        UIManager:close(self.image_widget)
    end
    local everywhere = Geom:new { x = 0, y = 0, w = width, h = height }
    self.image_widget = InputContainer:new {
        dimen = { x = 0, y = 0, w = width, h = height },
        ImageWidget:new { image = bitmap, image_disposable = true, width = width, height = height },
    }
    self.image_widget.ges_events = {
        QuietTap = { GestureRange:new { ges = "tap", range = everywhere } },
        QuietLeave = { GestureRange:new { ges = "hold", range = everywhere } },
    }
    self.image_widget.onQuietTap = function(_, _, ges)
        self:tap(ges.pos.x / width, ges.pos.y / height)
        return true
    end
    self.image_widget.onQuietLeave = function()
        self:stop()
        return true
    end
    UIManager:show(self.image_widget)
    UIManager:setDirty(self.image_widget, "ui")
end

--- A touch at (x, y), each 0 to 1 across the screen.
function Quiet:tap(x, y)
    for _, button in ipairs(self.buttons or {}) do
        if x >= button.x and x <= button.x + button.w and y >= button.y and y <= button.y + button.h then
            UIManager:show(InfoMessage:new { text = tostring(button.label or ""), timeout = 1 })
            NetworkMgr:runWhenConnected(function()
                local sent, reason = self:request(self.server .. "/kindle/tap", '{"id":"' .. tostring(button.id) .. '"}')
                if not sent then logger.warn("Quiet: tap not delivered:", reason) end
                self:schedule(AFTER_TAP_SECONDS)
            end)
            return
        end
    end
end

function Quiet:onSuspend()
    UIManager:unschedule(self.refresh_task)
end

function Quiet:onResume()
    if self.running then self:schedule(1) end
end

function Quiet:onCloseWidget()
    self:stop()
end

return Quiet
