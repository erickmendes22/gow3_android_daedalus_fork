/* Exercise SotC's original save backup/restore and mount quota in host sandbox. */
#define _GNU_SOURCE
#include "../src/runtime.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
static char rootdir[]="/tmp/sotc-save-test-XXXXXX";
const char *runtime_file_user_dir(void) { return rootdir; }
int runtime_file_mount(const char *guest,const char *host) { (void)guest; (void)host; return 0; }
void runtime_file_unmount(const char *guest) { (void)guest; }
uintptr_t runtime_lookup(const RuntimeExport *table,size_t count,const char *name) {
    for(size_t i=0;i<count;++i)
        if (!strcmp(name,table[i].name)) return (uintptr_t)table[i].function;
    return 0;
}
typedef struct {char data[32];} DirName;
typedef struct {char data[16];} MountPoint;
typedef struct {int32_t user,pad; const DirName *dir; uint64_t blocks; uint32_t mode;
                unsigned char reserved[32]; int32_t pad2;} Mount2;
typedef struct {MountPoint point;uint64_t required_blocks; uint32_t unused,status;
                unsigned char reserved[28];int32_t pad;} MountResult;
typedef struct {int32_t user,pad;const void *title;const DirName *dir;
                void *param,*icon;unsigned char reserved[32];} CheckBackup;
typedef struct {int32_t user,pad;const void *title;const DirName *dir;} RestoreBackup;
typedef int32_t (ABI *Init)(const void *);
typedef int32_t (ABI *Mount)(const Mount2 *,MountResult *);
typedef int32_t (ABI *Unmount)(const MountPoint *);
typedef int32_t (ABI *Query)(const MountPoint *,uint64_t *);
typedef int32_t (ABI *Check)(const CheckBackup *);
typedef int32_t (ABI *Restore)(const RestoreBackup *);
static void store(const char *path,const char *value) {
    FILE *f=fopen(path,"wb"); assert(f); assert(fwrite(value,1,strlen(value),f)==strlen(value)); assert(!fclose(f));
}
static void verify(const char *path,const char *expected) {
    char text[64]={0}; FILE *f=fopen(path,"rb"); assert(f);
    size_t n=fread(text,1,sizeof(text)-1,f); assert(!fclose(f));
    assert(n==strlen(expected) && !strcmp(text,expected));
}
int main(void) {
    assert(mkdtemp(rootdir));
    runtime_savedata_configure("CUSA08809");
    Init init=(Init)runtime_savedata_resolve("sceSaveDataInitialize");
    Mount mount=(Mount)runtime_savedata_resolve("sceSaveDataMount2");
    Unmount backup=(Unmount)runtime_savedata_resolve("sceSaveDataUmountWithBackup");
    Query query=(Query)runtime_savedata_resolve("sceSaveDataGetMountInfo");
    Check check=(Check)runtime_savedata_resolve("sceSaveDataCheckBackupData");
    Restore restore=(Restore)runtime_savedata_resolve("sceSaveDataRestoreBackupData");
    assert(init && mount && backup && query && check && restore);
    assert(init(NULL)==0);
    const DirName dir={"AUTOTEST"};
    const Mount2 args={.user=1000,.dir=&dir,.blocks=128,.mode=32};
    MountResult result={0};
    assert(mount(&args,&result)==0);
    uint64_t info[8]={0};
    assert(query(&result.point,info)==0);
    assert(info[0]>=96 && info[1]<=info[0]);
    char path[1024],backup_path[1024];
    snprintf(path,sizeof(path),"%s/savedata/1000/CUSA08809/AUTOTEST/progress.dat",rootdir);
    snprintf(backup_path,sizeof(backup_path),
             "%s/savedata/1000/CUSA08809/AUTOTEST.sce_backup/data/progress.dat",rootdir);
    store(path,"original progress");
    assert(backup(&result.point)==0);
    verify(backup_path,"original progress");
    store(path,"broken progress");
    const CheckBackup inspect={.user=1000,.dir=&dir};
    assert(check(&inspect)==0);
    const RestoreBackup recovery={.user=1000,.dir=&dir};
    assert(restore(&recovery)==0);
    verify(path,"original progress");
    puts("SotC savedata backup, restore and mount quota: PASS");
    return 0;
}
