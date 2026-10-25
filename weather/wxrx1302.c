/* wxrx1302: listen-only 2-FSK receiver on an SX1302/SX1250 LoRa concentrator (RAK5146 over USB, as in a FreedomFi
 * box), here pointed at a Fine Offset WH65B 7-in-1 weather station: 915.000 MHz, 17,241 bit/s, sync AA 2D D4.
 * Needs the raw-FSK patched sx1302_hal from zwave-sdr (sx1302/libloragw-sx1302-raw-fsk.patch: lgw_fsk_raw = fixed-length
 * blocks, no CRC, no whitening, no length byte). Never transmits.
 *
 * usage:  wxrx1302 SECONDS [inv]      inv = expect the opposite FSK polarity
 * env:    WX_DR (bit/s, default 11260), WX_SYNC (hex, default CACA54), WX_SYNCLEN (bytes, default 3),
 *         ZW_COM (serial port, default /dev/ttyACM0)
 * For the WH65B:  WX_DR=17241 WX_SYNC=AA2DD4 ./wxrx1302 3600 | python3 decode_wh65.py
 * Output: one line per received block: "<monotonic s> rssi <constant, ignore> size 40: <hex bytes>"
 */
#define _DEFAULT_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include "loragw_hal.h"
#include "loragw_reg.h"
extern int lgw_fsk_raw;
#define BLK 40
static int DR = 11260;
static unsigned long long SYNC = 0xCACA54; static int SYNCLEN = 3;
static struct lgw_pkt_tx_s txp;
static double wall(void) { struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts); return ts.tv_sec + ts.tv_nsec / 1e9; }
/* ---- radio ----------------------------------------------------------------------------- */
static int radio_start(void) {
    struct lgw_conf_board_s b; memset(&b, 0, sizeof b);
    b.lorawan_public = true; b.clksrc = 0; b.com_type = LGW_COM_USB; strcpy(b.com_path, getenv("ZW_COM") ? getenv("ZW_COM") : "/dev/ttyACM0");
    lgw_board_setconf(&b);
    struct lgw_conf_rxrf_s r; memset(&r, 0, sizeof r);
    r.enable = true; r.freq_hz = 915200000; r.rssi_offset = -215.4; r.type = LGW_RADIO_TYPE_SX1250; r.tx_enable = true;
    r.rssi_tcomp.coeff_c = 20.41; r.rssi_tcomp.coeff_d = 2162.56;
    lgw_rxrf_setconf(0, &r); r.tx_enable = false; lgw_rxrf_setconf(1, &r);
    struct lgw_conf_rxif_s f; memset(&f, 0, sizeof f);
    f.enable = true; f.rf_chain = 0; f.freq_hz = -200000; f.bandwidth = BW_125KHZ; f.datarate = DR;
    f.sync_word_size = SYNCLEN; f.sync_word = SYNC;
    if (lgw_rxif_setconf(9, &f)) return -1;
    struct lgw_tx_gain_lut_s lut; memset(&lut, 0, sizeof lut);
    int pidx = getenv("ZW_PWRIDX") ? atoi(getenv("ZW_PWRIDX")) : 3;
    lut.size = 1; lut.lut[0].pwr_idx = pidx; lut.lut[0].mix_gain = 5; lut.lut[0].dac_gain = 3;
    lgw_txgain_setconf(0, &lut);
    if (lgw_start() != LGW_HAL_SUCCESS) return -2;
    lgw_reg_w(SX1302_REG_RX_TOP_LORA_SERVICE_FSK_FSK_CFG_0_PKT_MODE, 0);
    lgw_reg_w(SX1302_REG_RX_TOP_LORA_SERVICE_FSK_FSK_CFG_0_CRC_EN, 0);
    lgw_reg_w(SX1302_REG_RX_TOP_LORA_SERVICE_FSK_FSK_CFG_0_DCFREE_ENC, 0);
    lgw_reg_w(SX1302_REG_RX_TOP_LORA_SERVICE_FSK_FSK_PKT_LENGTH_PKT_LENGTH, BLK);
    /* wait up to 1023 bit-times (HAL default 128) for the start marker after the preamble is
       detected: a battery thermostat's preamble is ~170 bits and was timing out every time */
    lgw_reg_w(SX1302_REG_RX_TOP_LORA_SERVICE_FSK_FSK_TIMEOUT_MSB_TIMEOUT, 3);
    lgw_reg_w(SX1302_REG_RX_TOP_LORA_SERVICE_FSK_FSK_TIMEOUT_LSB_TIMEOUT, 255);
    lgw_fsk_raw = 1;
    memset(&txp, 0, sizeof txp);
    txp.freq_hz = 915000000; txp.tx_mode = IMMEDIATE; txp.rf_chain = 0; txp.rf_power = 0;
    txp.modulation = MOD_FSK; txp.datarate = 40000; txp.f_dev = 20;
    return 0;
}


int main(int argc, char **argv) {
    double secs = argc > 1 ? atof(argv[1]) : 60;
    int inv = argc > 2 && !strcmp(argv[2], "inv");
    if (inv) SYNC = 0x3535AB;
    if (getenv("WX_DR")) DR = atoi(getenv("WX_DR"));
    if (getenv("WX_SYNC")) SYNC = strtoull(getenv("WX_SYNC"), NULL, 16);
    if (getenv("WX_SYNCLEN")) SYNCLEN = atoi(getenv("WX_SYNCLEN"));
    if (radio_start()) { fprintf(stderr, "radio start failed\n"); return 2; }
    fprintf(stderr, "wxrx1302: 915.000 MHz, %d bps, sync %06llX, listening %.0f s\n", DR, SYNC, secs);
    struct lgw_pkt_rx_s pk[8]; double end = wall() + secs; int n_all = 0;
    while (wall() < end) {
        int n = lgw_receive(8, pk);
        for (int i = 0; i < n; i++) {
            if (pk[i].modulation != MOD_FSK) continue;
            n_all++;
            printf("%.3f rssi %.0f size %u:", wall(), pk[i].rssic, pk[i].size);
            for (int k = 0; k < pk[i].size; k++) printf(" %02x", inv ? pk[i].payload[k] ^ 0xFF : pk[i].payload[k]);
            printf("\n"); fflush(stdout);
        }
        if (n == 0) usleep(2000);
    }
    lgw_stop();
    fprintf(stderr, "packets: %d\n", n_all);
    return 0;
}
