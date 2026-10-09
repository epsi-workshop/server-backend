"""Lance l'API sur le port 8000 en IPv4 et IPv6 à la fois (une seule socket « double pile »).

uvicorn n'écoute que sur une adresse : 0.0.0.0 (IPv4 seul) ou :: (IPv6 seul sur ce Debian).
Or talos.local annonce les deux (partage de connexion du téléphone) : selon la machine, le
client essaie l'une ou l'autre, d'où des « connexion refusée » aléatoires.
"""
import socket

import uvicorn

PORT = 8000

sock = socket.create_server(("", PORT), family=socket.AF_INET6, dualstack_ipv6=True, reuse_port=True)
config = uvicorn.Config("main:app", log_level="info")
uvicorn.Server(config).run(sockets=[sock])
