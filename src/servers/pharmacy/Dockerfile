FROM python:3.11-slim

WORKDIR /app

COPY src/servers/pharmacy/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Only the subtree the HTTP entrypoint actually imports: protocol/, the mcp
# method/model constants, and the pharmacy server itself. Keeps the image
# free of dependencies (httpx, the stdio transport) the remote server never
# uses.
COPY src/__init__.py ./src/__init__.py
COPY src/protocol ./src/protocol
COPY src/mcp/__init__.py ./src/mcp/__init__.py
COPY src/mcp/methods.py ./src/mcp/methods.py
COPY src/mcp/models.py ./src/mcp/models.py
COPY src/servers ./src/servers

ENV PORT=8080
EXPOSE 8080

CMD ["python", "-m", "src.servers.pharmacy.http_server"]
