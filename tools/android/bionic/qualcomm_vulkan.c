/* Reconstructed from the working Qualcomm APK's exported dispatch wrapper.
 * Native driver enumeration is the first point at which mapping is verified.
 * No system-driver fallback is accepted. */
#define _GNU_SOURCE
#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>
#include <dlfcn.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>

typedef void* (*AdrenoOpen)(int,int,const char*,const char*,const char*,const char*,const char*,void**);
static pthread_once_t loader_once=PTHREAD_ONCE_INIT;
static pthread_once_t mapping_once=PTHREAD_ONCE_INIT;
static PFN_vkGetInstanceProcAddr isolated_gipa;
static int selected_driver_mapped;
static void OpenQualcommDriver(void) {
    const char *path=getenv("GOW3_QUALCOMM_VULKAN_DRIVER");
    const char *hooks=getenv("GOW3_QUALCOMM_HOOK_DIR");
    const char *slash=path ? strrchr(path,'/') : NULL;
    if (!path || !hooks || !*hooks || !slash || !slash[1]) {
        fprintf(stderr,"Vulkan: imported Qualcomm driver configuration missing\n"); return;
    }
    char hook_dir[PATH_MAX], tool[PATH_MAX], driver_dir[PATH_MAX];
    size_t n=(size_t)(slash-path)+1;
    int h=snprintf(hook_dir,sizeof(hook_dir),"%s/",hooks);
    int t=snprintf(tool,sizeof(tool),"%s/libadrenotools.so",hooks);
    if(n>=sizeof(driver_dir)||h<0||t<0||h>=(int)sizeof(hook_dir)||t>=(int)sizeof(tool)){
        fprintf(stderr,"Vulkan: imported Qualcomm driver path is too long\n");return;
    }
    memcpy(driver_dir,path,n);driver_dir[n]=0;
    void *adreno=dlopen(tool,RTLD_NOW|RTLD_LOCAL);
    AdrenoOpen open=adreno?(AdrenoOpen)dlsym(adreno,"adrenotools_open_libvulkan"):NULL;
    if(!open){fprintf(stderr,"Vulkan: could not initialize imported Qualcomm loader: %s\n",dlerror());return;}
    void *loader=open(RTLD_NOW|RTLD_LOCAL,1,NULL,hook_dir,driver_dir,slash+1,NULL,NULL);
    if(!loader){fprintf(stderr,"Vulkan: imported Qualcomm vendor namespace initialization failed for %s\n",path);return;}
    isolated_gipa=(PFN_vkGetInstanceProcAddr)dlsym(loader,"vkGetInstanceProcAddr");
    fprintf(stderr,"Vulkan: imported Qualcomm isolated loader for %s (%s)\n",path,isolated_gipa?"ready":"no GIPA");
}
static void VerifySelectedDriver(void) {
    const char *selected=getenv("GOW3_QUALCOMM_VULKAN_DRIVER");
    char canonical[PATH_MAX],line[PATH_MAX+256];
    if(selected && realpath(selected,canonical)){
        FILE *maps=fopen("/proc/self/maps","r");
        if(maps){
            while(fgets(line,sizeof(line),maps)){
                char *p=strchr(line,'/');
                if(!p)continue;
                p[strcspn(p,"\r\n")]=0;
                if(strcmp(p,canonical)==0){selected_driver_mapped=1;break;}
            }
            fclose(maps);
        }
    }
    fprintf(stderr,"GoW III Qualcomm: %s: %s\n",selected_driver_mapped?"verified selected ICD mapped":"selected ICD was not mapped",selected?selected:"(null)");
}
static VKAPI_ATTR VkResult VKAPI_CALL EnumeratePhysicalDevices(VkInstance instance,uint32_t *count,VkPhysicalDevice *devices){
    PFN_vkEnumeratePhysicalDevices enumerate=(PFN_vkEnumeratePhysicalDevices)isolated_gipa(instance,"vkEnumeratePhysicalDevices");
    if(!enumerate)return VK_ERROR_INITIALIZATION_FAILED;
    VkResult result=enumerate(instance,count,devices);
    if((result==VK_SUCCESS || result==VK_INCOMPLETE) && count && *count){
        pthread_once(&mapping_once,VerifySelectedDriver);
        if(!selected_driver_mapped){*count=0;return VK_ERROR_INCOMPATIBLE_DRIVER;}
    }
    return result;
}
__attribute__((visibility("default"))) VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL vkGetInstanceProcAddr(VkInstance instance,const char *name){
    pthread_once(&loader_once,OpenQualcommDriver);
    if(!isolated_gipa || !name)return NULL;
    PFN_vkVoidFunction fn=isolated_gipa(instance,name);
    if(fn && strcmp(name,"vkEnumeratePhysicalDevices")==0)return (PFN_vkVoidFunction)EnumeratePhysicalDevices;
    return fn;
}
