#!/bin/sh
# Build wxrx1302 against the raw-FSK patched sx1302_hal.
# HAL = a checkout of Lora-net/sx1302_hal with zwave-sdr's sx1302/libloragw-sx1302-raw-fsk.patch applied and `make` run.
set -e
HAL=${HAL:-$HOME/sx1302_hal}
gcc -O2 -Wall -Wno-unused-function -Wno-unused-variable -I "$HAL/libloragw/inc" -o wxrx1302 wxrx1302.c \
    "$HAL/libloragw/libloragw.a" "$HAL/libtools/libtinymt32.a" "$HAL/libtools/libparson.a" "$HAL/libtools/libbase64.a" \
    -lm -lpthread -lrt
echo "built ./wxrx1302"
