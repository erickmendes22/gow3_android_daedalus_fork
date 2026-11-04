/* Exercise real Bionic guest mutex HLE, not an algorithm-only mock.
 * Build with -ffunction-sections -Wl,--gc-sections to avoid other HLE deps. */
#define _GNU_SOURCE
#include "../src/runtime_mutex.c"
#include <assert.h>
#include <stdio.h>
#include <unistd.h>
static __thread int32_t test_errno;
int32_t *runtime_errno(void) { return &test_errno; }
struct Args { GuestMutex **mutex; pthread_barrier_t *ready; };
static void *contender(void *p) {
    struct Args *a=p;
    pthread_barrier_wait(a->ready);
    assert(mutex_lock(a->mutex)==0);
    assert(mutex_unlock(a->mutex)==0);
    return NULL;
}
int main(int argc,char **argv) {
    assert(argc==2);
    assert(setenv("SOTC_MUTEX_SPIN_US",argv[1],1)==0);
    const unsigned want=(unsigned)strtoul(argv[1],NULL,10);
    assert(sotc_mutex_spin_budget()==want);
    GuestMutex *m=NULL;
    assert(mutex_init(&m,NULL,NULL)==0);
    for(int i=0;i<20;++i) {
        pthread_t t;pthread_barrier_t ready;
        assert(mutex_lock(&m)==0);
        assert(pthread_barrier_init(&ready,NULL,2)==0);
        struct Args arg={&m,&ready};
        assert(pthread_create(&t,NULL,contender,&arg)==0);
        pthread_barrier_wait(&ready);
        usleep(1000); /* force real contention and the original pthread fallback */
        assert(mutex_unlock(&m)==0);
        assert(pthread_join(t,NULL)==0);
        pthread_barrier_destroy(&ready);
    }
    assert(mutex_trylock(&m)==0);
    assert(mutex_unlock(&m)==0);
    assert(mutex_destroy(&m)==0);
    if(want) assert(__atomic_load_n(&sotc_spin_contended,__ATOMIC_RELAXED)>0);
    else assert(__atomic_load_n(&sotc_spin_contended,__ATOMIC_RELAXED)==0);
    printf("PASS: PC SotC mutex spin=%u us; 20 contended events, balanced locks/unlocks, blocking fallback intact\\n",want);
    return 0;
}
