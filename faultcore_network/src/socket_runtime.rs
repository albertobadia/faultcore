use crate::Endpoint;
use libc::{c_int, c_void, sockaddr, socklen_t};

pub fn socket_protocol_for_fd(fd: c_int) -> u64 {
    let mut sock_type: c_int = 0;
    let mut len = core::mem::size_of::<c_int>() as socklen_t;
    let rc = unsafe {
        libc::getsockopt(
            fd,
            libc::SOL_SOCKET,
            libc::SO_TYPE,
            (&mut sock_type as *mut c_int).cast::<c_void>(),
            &mut len,
        )
    };
    if rc < 0 {
        return 0;
    }
    match sock_type {
        libc::SOCK_STREAM => 1,
        libc::SOCK_DGRAM => 2,
        _ => 0,
    }
}

/// # Safety
/// `addr` must point to a valid socket address buffer of at least `addr_len` bytes.
pub unsafe fn sockaddr_ipv4(addr: *const sockaddr, addr_len: socklen_t) -> Option<(u32, u16)> {
    if addr.is_null() || addr_len < core::mem::size_of::<libc::sockaddr_in>() as socklen_t {
        return None;
    }
    let family = unsafe { (*addr).sa_family as c_int };
    if family != libc::AF_INET {
        return None;
    }
    let in_addr = unsafe { &*(addr.cast::<libc::sockaddr_in>()) };
    Some((u32::from_be(in_addr.sin_addr.s_addr), u16::from_be(in_addr.sin_port)))
}

pub fn peer_ipv4_for_fd(fd: c_int) -> Option<(u32, u16)> {
    let mut storage: libc::sockaddr_storage = unsafe { core::mem::zeroed() };
    let mut len = core::mem::size_of::<libc::sockaddr_storage>() as socklen_t;
    let rc = unsafe {
        libc::getpeername(
            fd,
            (&mut storage as *mut libc::sockaddr_storage).cast::<sockaddr>(),
            &mut len,
        )
    };
    if rc < 0 {
        return None;
    }
    unsafe { sockaddr_ipv4((&storage as *const libc::sockaddr_storage).cast::<sockaddr>(), len) }
}

pub fn monotonic_now_ns() -> u64 {
    let mut ts = libc::timespec {
        tv_sec: 0,
        tv_nsec: 0,
    };
    let rc = unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut ts) };
    if rc != 0 {
        return 0;
    }
    (ts.tv_sec as u64)
        .saturating_mul(1_000_000_000)
        .saturating_add(ts.tv_nsec as u64)
}

pub fn endpoint_for_fd(fd: c_int) -> Option<Endpoint> {
    let (ipv4, port) = peer_ipv4_for_fd(fd)?;
    Some(Endpoint {
        ipv4,
        port,
        protocol: socket_protocol_for_fd(fd),
    })
}

/// # Safety
/// `addr` must point to a valid socket address buffer of at least `addr_len` bytes.
pub unsafe fn endpoint_for_addr_or_fd(
    fd: c_int,
    addr: *const sockaddr,
    addr_len: socklen_t,
) -> Option<Endpoint> {
    let protocol = socket_protocol_for_fd(fd);
    let (ipv4, port) = unsafe { sockaddr_ipv4(addr, addr_len) }.or_else(|| peer_ipv4_for_fd(fd))?;
    Some(Endpoint {
        ipv4,
        port,
        protocol,
    })
}
