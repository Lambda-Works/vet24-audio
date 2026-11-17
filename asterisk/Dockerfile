# Asterisk 20.x comes from Ubuntu 24.04 "universe".
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=America/Argentina/Cordoba

# Package names confirmed on the host with apt-cache (noble/universe):
# asterisk-core-sounds-es-g722, asterisk-core-sounds-en. Both are needed:
# Spanish for voicemail prompts, English for the built-in "beep"/"vm-goodbye".
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asterisk \
        asterisk-config \
        asterisk-modules \
        asterisk-core-sounds-en \
        asterisk-core-sounds-es-g722 \
        sox \
        openssl \
        gettext-base \
        ca-certificates \
        tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && mkdir -p /usr/share/asterisk/moh \
    && rm -rf /var/lib/apt/lists/*

# Asterisk looks for languages under sounds/<lang>; the packages install
# region-specific directories. Link them (warn, do not fail, if missing).
RUN for pair in es:es_MX_f_Allison en:en_US_f_Allison; do \
        lang="${pair%%:*}"; dir="${pair##*:}"; base=/usr/share/asterisk/sounds; \
        if [ -e "$base/$lang" ]; then :; \
        elif [ -d "$base/$dir" ]; then ln -s "$dir" "$base/$lang"; \
        else echo "WARNING: $base/$dir not found; no '$lang' sounds link" >&2; fi; \
    done

COPY config/ /opt/lab/config/
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
