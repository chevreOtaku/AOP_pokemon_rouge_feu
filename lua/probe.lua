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
--   read8|16|32 <addr>   -> ok <valeur decimale>
--   dump <addr> <len>    -> ok <hexa majuscule, len octets>
--   blocks <a> <l> <b>   -> ok <somme par bloc de b octets>
--   err <message>        en cas d'echec
--
-- KEY : A B SELECT START RIGHT LEFT UP DOWN R L
--
-- ⚠ POURQUOI LES TROIS LECTURES BRUTES. Cette sonde ne savait rendre que la
-- position : chercher une adresse (le drapeau de combat, les PV adverses, le
-- curseur d'un menu) etait donc IMPOSSIBLE, faute de pouvoir regarder ailleurs.
-- Aucune carte memoire n'existe pour la version FR -- le pointeur ci-dessous a
-- ete trouve par scan et correlation, et les suivants le seront pareil.
--
-- La methode que ces trois commandes servent :
--   1. `blocks` sur une large plage, AVANT et APRES un changement connu ;
--   2. comparer les sommes -> seuls quelques blocs ont bouge ;
--   3. `dump` ces blocs-la, avant/apres, et comparer octet par octet ;
--   4. `read8/16/32` pour confirmer un candidat sur plusieurs situations.
-- Le tri se fait cote Python : la sonde ne decide rien, elle rend des octets.

local PORT = 9601

-- ⚠ LA SONDE DIT QUELLE SONDE ELLE EST, ET CE N'EST PAS DECORATIF.
-- Le 2026-08-12, mGBA a repondu `ping` et `state` tout en ignorant les
-- commandes de lecture memoire : une ancienne copie du script tournait encore
-- (le README propose de COLLER le contenu, et un « rechargement » ne relit
-- alors aucun fichier). Sans numero de version, « commande inconnue » est
-- indiscernable d'une faute de frappe. Avec, la question se tranche en un tour.
local VERSION = "2026-08-12 lecture-memoire"

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

-- ---------------------------------------------------------------- memoire

-- Regions lisibles d'une GBA. Une adresse hors de ces bornes n'est pas une
-- adresse : la refuser BRUYAMMENT vaut mieux que rendre un zero, parce qu'un
-- zero se lit comme une valeur et se compare comme une valeur.
local REGIONS = {
    { lo = 0x02000000, hi = 0x02040000, nom = "EWRAM" },
    { lo = 0x03000000, hi = 0x03008000, nom = "IWRAM" },
    { lo = 0x08000000, hi = 0x0A000000, nom = "ROM" },
}

-- ⚠ 1024 et pas 4096. `sock:send` peut n'ecrire qu'une PARTIE d'une longue
-- ligne et rendre le nombre d'octets ecrits -- une reponse tronquee au milieu
-- reste de l'hexadecimal valide, donc elle se relit comme des octets justes.
-- On envoie en boucle (voir `envoyer`) ET on garde des lignes courtes : le
-- surcout est quelques allers-retours de plus, le gain est qu'une troncature
-- devient impossible plutot que discrete.
local DUMP_MAX   = 1024      -- octets par `dump` (2048 caracteres hexa)
local BLOCKS_MAX = 262144    -- plage maximale balayee par `blocks`

-- Ecrit TOUT le texte, ou rend false. Borne pour ne jamais tourner sans fin.
local function envoyer(sock, texte)
    local reste, tours = texte, 0
    while #reste > 0 do
        tours = tours + 1
        if tours > 10000 then
            console:error("Envoi abandonne : le socket n'absorbe plus rien")
            return false
        end
        local n, err = sock:send(reste)
        if n then
            reste = reste:sub(n + 1)
        elseif err ~= socket.ERRORS.AGAIN then
            return false
        end
    end
    return true
end

local function region_de(addr, taille)
    for _, r in ipairs(REGIONS) do
        if addr >= r.lo and (addr + taille) <= r.hi then
            return r
        end
    end
    return nil
end

-- Accepte 0x02000000 comme 33554432.
-- ⚠ SANS BASE EXPLICITE, ET C'EST VOULU : `tonumber("0x20", 16)` rend nil,
-- parce qu'avec une base imposee Lua refuse le prefixe. Sans base, il comprend
-- l'hexadecimal nativement. Le piege est silencieux -- il rend nil, pas une
-- erreur -- donc il ressemblerait a une adresse mal tapee.
local function parse_addr(texte)
    if not texte or texte == "" then return nil end
    return tonumber(texte)
end

-- Rend une chaine d'octets, en une fois si mGBA le permet.
-- ⚠ `emu.readRange` n'existe pas partout, et sonder un champ absent sur un
-- userdata peut LEVER au lieu de rendre nil. On tente donc l'appel sous pcall
-- et on retombe sur la boucle octet par octet -- plus lente, toujours valable.
local function lire_octets(addr, len)
    local ok, res = pcall(function() return emu:readRange(addr, len) end)
    if ok and type(res) == "string" and #res == len then
        return res
    end
    local morceaux = {}
    for i = 0, len - 1 do
        morceaux[#morceaux + 1] = string.char(emu:read8(addr + i))
    end
    return table.concat(morceaux)
end

-- ---------------------------------------------------------------- requetes

local function handle(sock, line)
    local verb, arg1, arg2, arg3 = line:match("^(%S+)%s*(%S*)%s*(%S*)%s*(%S*)")
    verb = (verb or ""):lower()

    if verb == "ping" then
        sock:send("ok pong\n")
        return
    end

    if verb == "version" then
        sock:send("ok " .. VERSION .. "\n")
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

    if verb == "read8" or verb == "read16" or verb == "read32" then
        local taille = tonumber(verb:sub(5)) / 8
        local addr = parse_addr(arg1)
        if not addr then
            sock:send("err adresse illisible: " .. tostring(arg1) .. "\n")
            return
        end
        if not region_de(addr, taille) then
            sock:send(string.format("err adresse hors region lisible: 0x%08X\n", addr))
            return
        end
        local ok, valeur = pcall(function()
            if taille == 1 then return emu:read8(addr) end
            if taille == 2 then return emu:read16(addr) end
            return emu:read32(addr)
        end)
        if ok then
            sock:send("ok " .. tostring(valeur) .. "\n")
        else
            sock:send("err lecture impossible: " .. tostring(valeur) .. "\n")
        end
        return
    end

    if verb == "dump" then
        local addr = parse_addr(arg1)
        local len = tonumber(arg2)
        if not addr or not len then
            sock:send("err usage: dump <addr> <len>\n")
            return
        end
        if len < 1 or len > DUMP_MAX then
            sock:send("err longueur hors bornes (1-" .. DUMP_MAX .. ")\n")
            return
        end
        if not region_de(addr, len) then
            sock:send(string.format("err plage hors region lisible: 0x%08X+%d\n", addr, len))
            return
        end
        local ok, octets = pcall(lire_octets, addr, len)
        if not ok then
            sock:send("err lecture impossible: " .. tostring(octets) .. "\n")
            return
        end
        local hexa = {}
        for i = 1, #octets do
            hexa[i] = string.format("%02X", octets:byte(i))
        end
        envoyer(sock, "ok " .. table.concat(hexa) .. "\n")
        return
    end

    if verb == "blocks" then
        local addr = parse_addr(arg1)
        local len = tonumber(arg2)
        local taille_bloc = tonumber(arg3) or 256
        if not addr or not len then
            sock:send("err usage: blocks <addr> <len> [taille_bloc]\n")
            return
        end
        if len < 1 or len > BLOCKS_MAX then
            sock:send("err longueur hors bornes (1-" .. BLOCKS_MAX .. ")\n")
            return
        end
        if taille_bloc < 16 or taille_bloc > len then
            sock:send("err taille de bloc hors bornes (16.." .. len .. ")\n")
            return
        end
        if not region_de(addr, len) then
            sock:send(string.format("err plage hors region lisible: 0x%08X+%d\n", addr, len))
            return
        end
        -- Une somme par bloc : comparer deux releves designe les blocs qui ont
        -- bouge, sans transporter la memoire entiere sur le fil.
        local sommes = {}
        local ok, err = pcall(function()
            local pos = 0
            while pos < len do
                local n = math.min(taille_bloc, len - pos)
                local octets = lire_octets(addr + pos, n)
                local s = 0
                for i = 1, #octets do
                    s = (s + octets:byte(i) * i) % 4294967296
                end
                sommes[#sommes + 1] = tostring(s)
                pos = pos + n
            end
        end)
        if not ok then
            sock:send("err lecture impossible: " .. tostring(err) .. "\n")
            return
        end
        envoyer(sock, "ok " .. table.concat(sommes, " ") .. "\n")
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
        console:log("Sonde Rouge Feu FR [" .. VERSION .. "] -- port " .. PORT)
        console:log("Verifiez : python chasse.py verifier")
    end
end
