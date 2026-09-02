# Preview the Diya Meditation UI in a browser via noVNC.
# NOTE: For development/preview/sharing only — NOT the real kiosk deployment.
#
# Build (context = the project folder):
#   docker build -t diya-meditation -f docker/Dockerfile .
# Run:
#   docker run --rm -p 8080:8080 diya-meditation
#   then open http://localhost:8080/vnc.html
#
FROM mcr.microsoft.com/dotnet/sdk:8.0

# X server (virtual), VNC + web bridge, and the X libs Avalonia needs.
RUN apt-get update && apt-get install -y --no-install-recommends \
      xvfb x11vnc novnc websockify \
      libx11-6 libxext6 libxrender1 libxi6 libxrandr2 libxcursor1 libxss1 \
      libice6 libsm6 libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY . ./
RUN dotnet publish DiyaMeditation.csproj -c Release -o /app \
 && chmod +x docker/entrypoint.sh

ENV DISPLAY=:99
EXPOSE 8080
CMD ["/src/docker/entrypoint.sh"]
