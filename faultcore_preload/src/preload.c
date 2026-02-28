#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <dlfcn.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <arpa/inet.h>
#include <time.h>
#include <pthread.h>
#include <errno.h>

typedef struct {
    long tv_sec;
    long tv_usec;
} faultcore_timeval_t;

static volatile int latency_ms = 0;
static volatile double packet_loss_percent = 0.0;
static volatile int bandwidth_kbps = 0;
static volatile int jitter_ms = 0;
static volatile int initialized = 0;

static pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;

static void init_from_env(void) {
    if (initialized) return;
    
    pthread_mutex_lock(&mutex);
    if (initialized) {
        pthread_mutex_unlock(&mutex);
        return;
    }
    
    char *env;
    
    env = getenv("FAULTCORE_LATENCY_MS");
    if (env) latency_ms = atoi(env);
    
    env = getenv("FAULTCORE_PACKET_LOSS");
    if (env) packet_loss_percent = atof(env);
    
    env = getenv("FAULTCORE_BANDWIDTH_KBPS");
    if (env) bandwidth_kbps = atoi(env);
    
    env = getenv("FAULTCORE_JITTER_MS");
    if (env) jitter_ms = atoi(env);
    
    initialized = 1;
    pthread_mutex_unlock(&mutex);
}

static void apply_latency(void) {
    if (latency_ms <= 0 && jitter_ms <= 0) return;
    
    int total_ms = latency_ms;
    if (jitter_ms > 0) {
        total_ms += (rand() % (jitter_ms * 2 + 1)) - jitter_ms;
    }
    if (total_ms < 0) total_ms = 0;
    
    usleep(total_ms * 1000);
}

static int should_drop_packet(void) {
    if (packet_loss_percent <= 0.0) return 0;
    
    double random = (double)rand() / (double)RAND_MAX;
    return random < (packet_loss_percent / 100.0);
}

static ssize_t (*real_send)(int sockfd, const void *buf, size_t len, int flags);
static ssize_t (*real_recv)(int sockfd, void *buf, size_t len, int flags);
static int (*real_connect)(int sockfd, const struct sockaddr *addr, socklen_t addrlen);
static ssize_t (*real_sendto)(int sockfd, const void *buf, size_t len, int flags, const struct sockaddr *dest_addr, socklen_t addrlen);
static ssize_t (*real_recvfrom)(int sockfd, void *buf, size_t len, int flags, struct sockaddr *src_addr, socklen_t *addrlen);

static void init_real_functions(void) {
    if (real_send) return;
    
    real_send = dlsym(RTLD_NEXT, "send");
    real_recv = dlsym(RTLD_NEXT, "recv");
    real_connect = dlsym(RTLD_NEXT, "connect");
    real_sendto = dlsym(RTLD_NEXT, "sendto");
    real_recvfrom = dlsym(RTLD_NEXT, "recvfrom");
}

__attribute__((constructor))
static void faultcore_preload_init(void) {
    init_from_env();
    init_real_functions();
    srand(time(NULL));
}

ssize_t send(int sockfd, const void *buf, size_t len, int flags) {
    init_from_env();
    init_real_functions();
    
    if (should_drop_packet()) {
        return len;
    }
    
    apply_latency();
    
    return real_send(sockfd, buf, len, flags);
}

ssize_t recv(int sockfd, void *buf, size_t len, int flags) {
    init_from_env();
    init_real_functions();
    
    apply_latency();
    
    ssize_t result = real_recv(sockfd, buf, len, flags);
    
    if (result > 0 && should_drop_packet()) {
        memset(buf, 0, result);
        return 0;
    }
    
    return result;
}

int connect(int sockfd, const struct sockaddr *addr, socklen_t addrlen) {
    init_from_env();
    init_real_functions();
    
    apply_latency();
    
    return real_connect(sockfd, addr, addrlen);
}

ssize_t sendto(int sockfd, const void *buf, size_t len, int flags, const struct sockaddr *dest_addr, socklen_t addrlen) {
    init_from_env();
    init_real_functions();
    
    if (should_drop_packet()) {
        return len;
    }
    
    apply_latency();
    
    return real_sendto(sockfd, buf, len, flags, dest_addr, addrlen);
}

ssize_t recvfrom(int sockfd, void *buf, size_t len, int flags, struct sockaddr *src_addr, socklen_t *addrlen) {
    init_from_env();
    init_real_functions();
    
    apply_latency();
    
    ssize_t result = real_recvfrom(sockfd, buf, len, flags, src_addr, addrlen);
    
    if (result > 0 && should_drop_packet()) {
        memset(buf, 0, result);
        return 0;
    }
    
    return result;
}
