#!/usr/bin/env bash

# Установка модуля поддержки HentaiLib.
mkdir Parsers/hentailib
cp Parsers/mangalib/modules/hentailib.py Parsers/hentailib/main.py
cp Parsers/mangalib/modules/hentailib_manifest.json Parsers/hentailib/manifest.json
cp Parsers/mangalib/settings.json Parsers/hentailib/settings.json
# Установка модуля поддержки SlashLib.
mkdir Parsers/slashlib
cp Parsers/mangalib/modules/slashlib.py Parsers/slashlib/main.py
cp Parsers/mangalib/modules/slashlib_manifest.json Parsers/slashlib/manifest.json
cp Parsers/mangalib/settings.json Parsers/slashlib/settings.json