from ldap3 import Server, Connection, ALL

server = Server(
    '202.28.50.28',
    get_info=ALL
)

conn = Connection(
    server,
    auto_bind=True
)

print("CONNECTED")

print(server.info)