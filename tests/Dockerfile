# mason test sandbox: ubuntu + claude cli + chisel + deb tooling.
# modelled on ~/git/pats images/Dockerfile.sandbox-26.04, plus what the
# chisel-releases skill needs at runtime: python3 + dpkg-deb (deb-list) and
# the chisel binary (try-cut).
#
# clis installed globally (npm -g) so they're on PATH for any uid -- pats runs
# the container with `--user <host uid>`, which has no home of its own.
#
# build locally (pats image not published yet):
#   docker build -t mason-test/sandbox:26.04 tests/
FROM docker.io/library/ubuntu:26.04

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        nodejs \
        npm \
        python3 \
        dpkg-dev && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

ARG CLAUDE_CLI_VERSION=latest
RUN npm install -g "@anthropic-ai/claude-code@${CLAUDE_CLI_VERSION}" && \
    npm cache clean --force

# chisel: latest release binary for the build arch (try-cut needs it).
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    ver="$(curl -fsSL https://api.github.com/repos/canonical/chisel/releases/latest \
           | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p')"; \
    curl -fsSL "https://github.com/canonical/chisel/releases/download/${ver}/chisel_${ver}_linux_${arch}.tar.gz" \
         -o /tmp/chisel.tgz; \
    tar -xzf /tmp/chisel.tgz -C /usr/local/bin chisel; \
    rm /tmp/chisel.tgz; \
    chisel version

CMD ["/bin/bash"]
