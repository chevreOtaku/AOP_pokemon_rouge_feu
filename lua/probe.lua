-- probe.lua -- les yeux et les mains, dans l'emulateur.
--
-- A charger dans mGBA : Outils > Scripting > (coller, ou File > Load).
-- Ouvre un serveur TCP et repond a des requetes ligne par ligne. Aucun
-- fichier, aucun polling : la moitie Python demande, ce script repond.
--
-- Protocole (une ligne par requete, une ligne par reponse) :
--   ping                 -> ok pong
--   state                -> ok x=<n> y=<n> g=<n> n=<n>
--   press <KEY> [frames] -> ok x=<n> y=<n> g=<n> n=<n>   (etat APRES stabilisation)
--   err <message>        en cas d'echec
--
-- KEY : A B SELECT START RIGHT LEFT UP DOWN R L

local PORT = 9601

-- Pointeur du SaveBlock1 de Pokemon Rouge Feu (FR).
-- Trouve par scan+correlation le 2026-07-08, pas par documentation.
-- Rouge Feu DEMENAGE ses SaveBlocks en cours de partie : on relit le
-- pointeur a chaque lecture et on ne cache JAMAIS l'adresse resolue.
local PTR_ADDR  = 0x03004F58
local EWRAM_LO  = 0x02000000
local EWRAM_HI  = 0x02040000

-- Ordre des bits : enum GBAKey, include/mgba/internal/gba/input.h.
-- Lu a la source et non devine : l'exemple socketserver.lua livre avec
-- mGBA affiche "<" a l'indice du bit RIGHT, son etiquetage est trompeur.
local KEYS = {
    A = 0, B = 1, SELECT = 2, START = 3,
    RIGHT = 4, LEFT = 5, UP = 6, DOWN = 7,
    R = 8, L = 9,
}

-- Un pas fait ~16 frames sur GBA. On maintient la touche, PUIS on laisse
-- le monde se stabiliser avant de lire : sinon on lit au milieu du pas et
-- l'avant/apres ne veut rien dire.
local PRESS_FRAMES_DEFAULT = 16
local SETTLE_FRAMES        = 10

local server = nil
local clients = {}
local pending = nil   -- { sock, mask, hold, settle }

-- ---------------------------------------------------------------- lecture

-- Rend x, y, mapGroup, mapNum -- ou nil si le pointeur est invalide.
-- mapGroup == 255 signale une transition de porte (etat instable).
local function read_state()
    local ok, res = pcall(function()
        local p = emu:read32(PTR_ADDR)
        if p < EWRAM_LO or p >= EWRAM_HI then
            return nil
        end
        return {
            x = emu:read16(p),
            y = emu:read16(p + 2),
            g = emu:read8(p + 4),
            n = emu:read8(p + 5),
        }
    end)
    if ok then return res end
    return nil
end

local function state_line(st)
    if not st then
        return "err pointeur invalide (SaveBlock non resolu)"
    end
    return string.format("ok x=%d y=%d g=%d n=%d", st.x, st.y, st.g, st.n)
end

-- ---------------------------------------------------------------- requetes

local function handle(sock, line)
    local verb, arg1, arg2 = line:match("^(%S+)%s*(%S*)%s*(%S*)")
    verb = (verb or ""):lower()

    if verb == "ping" then
        sock:send("ok pong\n")
        return
    end

    if verb == "state" then
        sock:send(state_line(read_state()) .. "\n")
        return
    end

    if verb == "press" then
        if pending then
            sock:send("err une pression est deja en cours\n")
            return
        end
        local bit = KEYS[(arg1 or ""):upper()]
        if not bit then
            sock:send("err touche inconnue: " .. tostring(arg1) .. "\n")
            return
        end
        local frames = tonumber(arg2) or PRESS_FRAMES_DEFAULT
        if frames < 1 or frames > 600 then
            sock:send("err duree hors bornes (1-600 frames)\n")
            return
        end
        local mask = 1 << bit
        emu:setKeys(mask)
        pending = { sock = sock, hold = frames, settle = SETTLE_FRAMES }
        -- La reponse part quand le monde s'est stabilise (voir on_frame).
        return
    end

    sock:send("err commande inconnue: " .. tostring(verb) .. "\n")
end

-- ---------------------------------------------------------------- frames

local function on_frame()
    if not pending then return end

    if pending.hold > 0 then
        pending.hold = pending.hold - 1
        if pending.hold == 0 then
            emu:setKeys(0)   -- relache tout ; setKeys est sur, clearKeys non verifie
        end
        return
    end

    pending.settle = pending.settle - 1
    if pending.settle > 0 then return end

    local sock = pending.sock
    pending = nil
    local ok = pcall(function()
        sock:send(state_line(read_state()) .. "\n")
    end)
    if not ok then
        console:error("Reponse impossible : client parti pendant la pression")
    end
end

-- ---------------------------------------------------------------- sockets

local function on_received(id)
    local sock = clients[id]
    if not sock then return end
    while true do
        local p, err = sock:receive(512)
        if p then
            for line in p:gmatch("[^\r\n]+") do
                handle(sock, line)
            end
        else
            if err ~= socket.ERRORS.AGAIN then
                clients[id] = nil
                if pending and pending.sock == sock then
                    emu:setKeys(0)
                    pending = nil
                end
                sock:close()
            end
            return
        end
    end
end

local function on_accept()
    local sock, err = server:accept()
    if err then
        console:error("accept: " .. tostring(err))
        return
    end
    local id = #clients + 1
    clients[id] = sock
    sock:add("received", function() on_received(id) end)
    sock:add("error", function() clients[id] = nil end)
    console:log("Client connecte")
end

-- Port FIXE, echec BRUYANT. On ne reprend PAS l'auto-increment de
-- socketserver.lua : un port qui bouge tout seul, c'est une moitie Python
-- qui se connecte ailleurs -- ou nulle part -- sans que rien ne le dise.
local err
server, err = socket.bind(nil, PORT)
if err then
    console:error("Impossible d'ouvrir le port " .. PORT .. " : " .. tostring(err))
    console:error("Rien n'ecoute. Liberez le port plutot que d'en changer.")
else
    local ok
    ok, err = server:listen()
    if err then
        server:close()
        server = nil
        console:error("listen: " .. tostring(err))
    else
        server:add("received", on_accept)
        callbacks:add("frame", on_frame)
        console:log("Sonde Rouge Feu FR -- ecoute sur le port " .. PORT)
        console:log("Verifiez d'abord : 'state' doit rendre des coordonnees plausibles.")
    end
end
