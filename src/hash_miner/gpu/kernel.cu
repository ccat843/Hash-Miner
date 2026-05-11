extern "C" {
__device__ __forceinline__ unsigned long long rotl64(unsigned long long x, int s){ return (x << s) | (x >> (64 - s)); }
__constant__ unsigned char d_challenge[32];

__device__ __forceinline__ void keccakf(unsigned long long st[25]) {
    const unsigned long long RC[24] = {
        0x0000000000000001ULL,0x0000000000008082ULL,0x800000000000808aULL,0x8000000080008000ULL,
        0x000000000000808bULL,0x0000000080000001ULL,0x8000000080008081ULL,0x8000000000008009ULL,
        0x000000000000008aULL,0x0000000000000088ULL,0x0000000080008009ULL,0x000000008000000aULL,
        0x000000008000808bULL,0x800000000000008bULL,0x8000000000008089ULL,0x8000000000008003ULL,
        0x8000000000008002ULL,0x8000000000000080ULL,0x000000000000800aULL,0x800000008000000aULL,
        0x8000000080008081ULL,0x8000000000008080ULL,0x0000000080000001ULL,0x8000000080008008ULL
    };
    const int r[25] = {0,1,62,28,27,36,44,6,55,20,3,10,43,25,39,41,45,15,21,8,18,2,61,56,14};
    for (int round=0; round<24; ++round) {
        unsigned long long c[5], d[5], b[25];
        #pragma unroll
        for(int x=0;x<5;++x) c[x]=st[x]^st[x+5]^st[x+10]^st[x+15]^st[x+20];
        #pragma unroll
        for(int x=0;x<5;++x){ d[x]=c[(x+4)%5]^rotl64(c[(x+1)%5],1); }
        #pragma unroll
        for(int i=0;i<25;++i) st[i]^=d[i%5];
        #pragma unroll
        for(int x=0;x<5;++x) for(int y=0;y<5;++y) b[y+5*((2*x+3*y)%5)] = rotl64(st[x+5*y], r[x+5*y]);
        #pragma unroll
        for(int x=0;x<5;++x) for(int y=0;y<5;++y) st[x+5*y] = b[x+5*y] ^ ((~b[((x+1)%5)+5*y]) & b[((x+2)%5)+5*y]);
        st[0] ^= RC[round];
    }
}

__device__ __forceinline__ void absorb_challenge_nonce(unsigned long long nonce, unsigned long long st[25]) {
    unsigned char msg[64] = {0};
    #pragma unroll
    for(int i=0;i<32;i++) msg[i]=d_challenge[i];
    #pragma unroll
    for(int i=0;i<8;i++) msg[63-i] = (unsigned char)((nonce >> (8*i)) & 0xffULL);
    #pragma unroll
    for(int i=0;i<8;i++){
        unsigned long long lane=0;
        #pragma unroll
        for(int b=0;b<8;b++) lane |= ((unsigned long long)msg[i*8+b]) << (8*b);
        st[i]=lane;
    }
    #pragma unroll
    for(int i=8;i<25;i++) st[i]=0;
    st[8] = 0x01ULL;
    st[16] ^= 0x8000000000000000ULL;
}

__device__ __forceinline__ bool lt_u256(unsigned long long h3,unsigned long long h2,unsigned long long h1,unsigned long long h0,
                                        unsigned long long d3,unsigned long long d2,unsigned long long d1,unsigned long long d0){
    if (h3 != d3) return h3 < d3;
    if (h2 != d2) return h2 < d2;
    if (h1 != d1) return h1 < d1;
    return h0 < d0;
}

__global__ void mine_keccak_kernel(unsigned long long nonce_base, unsigned long long total_threads,
                                   unsigned long long d3, unsigned long long d2, unsigned long long d1, unsigned long long d0,
                                   unsigned long long* out_nonce, int* found_flag) {
    unsigned long long gid = blockIdx.x * blockDim.x + threadIdx.x;
    if (gid >= total_threads || atomicAdd(found_flag, 0)) return;
    unsigned long long nonce = nonce_base + gid;
    unsigned long long st[25];
    absorb_challenge_nonce(nonce, st);
    keccakf(st);
    unsigned long long h0=st[0], h1=st[1], h2=st[2], h3=st[3];
    if (lt_u256(h3,h2,h1,h0,d3,d2,d1,d0)) {
        if (atomicCAS(found_flag, 0, 1) == 0) out_nonce[0] = nonce;
    }
}

__global__ void sample_hashes_kernel(const unsigned long long* nonces, unsigned long long n, unsigned char* out_hashes) {
    unsigned long long i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n) return;
    unsigned long long st[25];
    absorb_challenge_nonce(nonces[i], st);
    keccakf(st);
    unsigned char* out = out_hashes + i*32;
    #pragma unroll
    for (int w=0; w<4; ++w) {
        unsigned long long v = st[w];
        #pragma unroll
        for (int b=0; b<8; ++b) out[w*8+b] = (unsigned char)((v >> (8*b)) & 0xffULL);
    }
}
}
