/* The Order: 1886 Bionic Pad HLE — no SDL dependency.
 * Preserves the title's 120-byte scePadData ABI and 943-line touch surface.
 * Input is the atomically replaced state file written by the Android game activity.
 * Adapted from the existing FEX Android pad-file protocol, without GoW game logic.
 */
#ifdef __ANDROID__
#define _GNU_SOURCE
#include "runtime.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <time.h>
#include <sys/stat.h>
#include <errno.h>

#define ERR_INVALID_ARG ((int32_t)0x80920001)
#define ERR_INVALID_HANDLE ((int32_t)0x80920003)
#define ERR_ALREADY_OPENED ((int32_t)0x80920004)
#define ERR_NOT_INITIALIZED ((int32_t)0x80920005)
#define PAD_HANDLE 1
enum {
    BTN_L3=0x2, BTN_R3=0x4, BTN_OPTIONS=0x8, BTN_UP=0x10, BTN_RIGHT=0x20,
    BTN_DOWN=0x40, BTN_LEFT=0x80, BTN_L2=0x100, BTN_R2=0x200,
    BTN_L1=0x400, BTN_R1=0x800, BTN_TRIANGLE=0x1000, BTN_CIRCLE=0x2000,
    BTN_CROSS=0x4000, BTN_SQUARE=0x8000, BTN_TOUCHPAD=0x100000,
};
typedef struct { uint16_t x,y; uint8_t id,reserve[3]; } PadTouch;
typedef struct {
    uint32_t buttons;
    uint8_t left_x,left_y,right_x,right_y;
    uint8_t l2,r2,analog_padding[2];
    float orientation[4],acceleration[3],angular_velocity[3];
    uint8_t touch_count,touch_reserve[3];
    uint32_t touch_held_time;
    PadTouch touches[2];
    uint8_t connected,pad0[3];
    uint64_t timestamp;
    uint8_t extension[16];
    uint8_t connected_count,reserve[2],unique_length,unique[12];
} PadData;
typedef struct {
    float pixel_density; uint16_t resolution_x,resolution_y;
    uint8_t dead_zone_left,dead_zone_right,connection_type,connected_count;
    uint8_t connected,pad[3]; int32_t device_class; uint8_t reserve[8];
} ControllerInfo;
_Static_assert(sizeof(PadData)==120,"The Order 1886 PadData ABI");
_Static_assert(__builtin_offsetof(PadData,touches)==60,"PS4 touch array offset");
_Static_assert(__builtin_offsetof(PadData,timestamp)==80,"PS4 pad timestamp offset");
_Static_assert(sizeof(ControllerInfo)==28,"PS4 controller info ABI");

static pthread_mutex_t pad_lock=PTHREAD_MUTEX_INITIALIZER;
static int initialized,opened;
static unsigned long long reads;
static uint64_t now_us(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC,&t);
    return (uint64_t)t.tv_sec*1000000u+(uint64_t)t.tv_nsec/1000u;
}
typedef struct {
    uint32_t buttons;
    uint8_t axes[4], l2, r2;
    int touch_down, touch_click;
    uint16_t touch_x,touch_y;
} PadState;
static PadState state={0,{128,128,128,128},0,0,0,0,960,471};
static uint64_t last_check;
static struct timespec last_mod;
static off_t last_size=-1;
static const struct { const char *name; uint32_t bits; } keymap[] = {
    {"cross",BTN_CROSS},{"circle",BTN_CIRCLE},{"square",BTN_SQUARE},
    {"triangle",BTN_TRIANGLE},{"l1",BTN_L1},{"r1",BTN_R1},
    {"l2",BTN_L2},{"r2",BTN_R2},{"l3",BTN_L3},{"r3",BTN_R3},
    {"options",BTN_OPTIONS},{"up",BTN_UP},{"down",BTN_DOWN},
    {"left",BTN_LEFT},{"right",BTN_RIGHT},
};
static uint8_t clamp8(int v) { return (uint8_t)(v<0?0:v>255?255:v); }
static uint16_t clamp_touch(int v,int maximum) {
    return (uint16_t)(v<0?0:v>maximum?maximum:v);
}
static void read_pad_file(void) {
    static const char *path;
    static int init;
    if(!init){path=getenv("ORDER1886_PAD_FILE");init=1;}
    if(!path||!*path)return;
    uint64_t now=now_us();
    if(now-last_check<10000)return;
    last_check=now;
    struct stat st;
    if(stat(path,&st)!=0) {
        state=(PadState){0,{128,128,128,128},0,0,0,0,960,471};
        return;
    }
    if(st.st_mtim.tv_sec==last_mod.tv_sec &&
       st.st_mtim.tv_nsec==last_mod.tv_nsec &&
       st.st_size==last_size) return;
    FILE *f=fopen(path,"r");
    if(!f)return;
    PadState next={0,{128,128,128,128},0,0,0,0,960,471};
    char token[96];
    while(fscanf(f,"%95s",token)==1) {
        for(size_t i=0;i<sizeof(keymap)/sizeof(keymap[0]);++i)
            if(!strcmp(token,keymap[i].name))next.buttons|=keymap[i].bits;
        if(!strcmp(token,"touchpad") || !strcmp(token,"touchpad_left")) {
            next.touch_down=next.touch_click=1;next.touch_x=480;next.touch_y=471;
        } else if(!strcmp(token,"touchpad_right")) {
            next.touch_down=next.touch_click=1;next.touch_x=1440;next.touch_y=471;
        } else if(!strncmp(token,"lx=",3))next.axes[0]=clamp8(atoi(token+3));
        else if(!strncmp(token,"ly=",3))next.axes[1]=clamp8(atoi(token+3));
        else if(!strncmp(token,"rx=",3))next.axes[2]=clamp8(atoi(token+3));
        else if(!strncmp(token,"ry=",3))next.axes[3]=clamp8(atoi(token+3));
        else if(!strncmp(token,"l2=",3))next.l2=clamp8(atoi(token+3));
        else if(!strncmp(token,"r2=",3))next.r2=clamp8(atoi(token+3));
        else if(!strncmp(token,"touch_down=",11))next.touch_down=atoi(token+11)!=0;
        else if(!strncmp(token,"touch_click=",12))next.touch_click=atoi(token+12)!=0;
        else if(!strncmp(token,"touch_x=",8))next.touch_x=clamp_touch(atoi(token+8),1919);
        else if(!strncmp(token,"touch_y=",8))next.touch_y=clamp_touch(atoi(token+8),942);
    }
    fclose(f);
    if(next.l2>30)next.buttons|=BTN_L2;
    if(next.r2>30)next.buttons|=BTN_R2;
    if(next.buttons&BTN_L2)next.l2=255;
    if(next.buttons&BTN_R2)next.r2=255;
    state=next;
    last_mod=st.st_mtim;last_size=st.st_size;
}
static void sample(PadData *d) {
    read_pad_file();
    memset(d,0,sizeof(*d));
    d->buttons=state.buttons|(state.touch_click?BTN_TOUCHPAD:0);
    d->left_x=state.axes[0];d->left_y=state.axes[1];
    d->right_x=state.axes[2];d->right_y=state.axes[3];
    d->l2=state.l2;d->r2=state.r2;
    d->orientation[3]=1.0f;
    d->connected=1;d->connected_count=1;
    d->timestamp=now_us();
    if(state.touch_down) {
        d->touch_count=1;
        d->touches[0]=(PadTouch){.x=state.touch_x,.y=state.touch_y,.id=0};
    }
}
static ABI int32_t pad_init(void) {
    pthread_mutex_lock(&pad_lock);initialized=1;pthread_mutex_unlock(&pad_lock);
    return 0;
}
static ABI int32_t pad_open(int32_t user,int32_t type,int32_t index,const void *param) {
    (void)param;
    if(!initialized)return ERR_NOT_INITIALIZED;
    if(user!=1 || (type!=0&&type!=2) || index)return ERR_INVALID_ARG;
    pthread_mutex_lock(&pad_lock);
    int was_open=opened;opened=1;
    pthread_mutex_unlock(&pad_lock);
    if(was_open)return ERR_ALREADY_OPENED;
    puts("Runtime: The Order PS4 pad opened via Android PadBridge");
    return PAD_HANDLE;
}
static ABI int32_t pad_close(int32_t handle) {
    if(handle!=PAD_HANDLE||!opened)return ERR_INVALID_HANDLE;
    pthread_mutex_lock(&pad_lock);opened=0;pthread_mutex_unlock(&pad_lock);return 0;
}
static ABI int32_t pad_read_state(int32_t handle,PadData *data) {
    if(handle!=PAD_HANDLE||!opened)return ERR_INVALID_HANDLE;
    if(!data)return ERR_INVALID_ARG;
    pthread_mutex_lock(&pad_lock);sample(data);++reads;pthread_mutex_unlock(&pad_lock);
    return 0;
}
static ABI int32_t pad_read(int32_t handle,PadData *data,int32_t count) {
    if(handle!=PAD_HANDLE||!opened)return ERR_INVALID_HANDLE;
    if(!data||count<1||count>64)return ERR_INVALID_ARG;
    pad_read_state(handle,data);return 1;
}
static ABI int32_t pad_info(int32_t handle,ControllerInfo *info) {
    if(handle!=PAD_HANDLE||!opened)return ERR_INVALID_HANDLE;
    if(!info)return ERR_INVALID_ARG;
    memset(info,0,sizeof(*info));info->pixel_density=44.86f;
    info->resolution_x=1920;info->resolution_y=943;
    info->dead_zone_left=info->dead_zone_right=2;
    info->connected_count=info->connected=1;
    return 0;
}
static ABI int32_t pad_vibration(int32_t handle,const uint8_t *param) {
    if(handle!=PAD_HANDLE||!opened)return ERR_INVALID_HANDLE;
    if(!param)return ERR_INVALID_ARG;
    return 0; /* Android UI-side rumble bridge to be wired. */
}
static ABI int32_t pad_ok_handle(int32_t handle) {return handle==PAD_HANDLE&&opened?0:ERR_INVALID_HANDLE;}
static ABI int32_t pad_ok_handle_flag(int32_t h,uint8_t flag) {(void)flag;return pad_ok_handle(h);}
static ABI int32_t pad_light_bar(int32_t h,const uint8_t *rgb) {
    if(h!=PAD_HANDLE||!opened)return ERR_INVALID_HANDLE;
    (void)rgb;return 0;
}
static const RuntimeExport exports[]={
    {"scePadSetLightBar",pad_light_bar},{"scePadResetLightBar",pad_ok_handle},
    {"scePadInit",pad_init},{"scePadOpen",pad_open},{"scePadClose",pad_close},
    {"scePadReadState",pad_read_state},{"scePadRead",pad_read},
    {"scePadGetControllerInformation",pad_info},{"scePadSetVibration",pad_vibration},
    {"scePadResetOrientation",pad_ok_handle},
    {"scePadSetAngularVelocityDeadbandState",pad_ok_handle_flag},
    {"scePadSetTiltCorrectionState",pad_ok_handle_flag},
    {"scePadSetMotionSensorState",pad_ok_handle_flag},
};
uintptr_t runtime_pad_resolve(const char *name) {return RUNTIME_LOOKUP(exports,name);}
void runtime_pad_report(void) {
    printf("Runtime: PS4 pad reads=%llu, source=Android PadBridge\n",reads);
}
#endif /* __ANDROID__ */
