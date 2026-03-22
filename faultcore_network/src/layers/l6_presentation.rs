use crate::layers::{
    Direction, Layer, LayerDecision, LayerStage, Mutation, MutationKind, MutationTarget,
    PacketContext,
};

pub struct L6Presentation;

impl L6Presentation {
    pub fn new() -> Self {
        Self
    }
}

impl Default for L6Presentation {
    fn default() -> Self {
        Self::new()
    }
}

impl Layer for L6Presentation {
    fn stage(&self) -> LayerStage {
        LayerStage::L6
    }

    fn process(&self, _ctx: &PacketContext<'_>) -> LayerDecision {
        LayerDecision::Continue
    }

    fn process_with_buffer(
        &self,
        ctx: &PacketContext<'_>,
        buffer: &[u8],
    ) -> (LayerDecision, Option<Vec<u8>>) {
        if buffer.is_empty() || ctx.is_connect() || ctx.is_dns() {
            return (LayerDecision::Continue, None);
        }

        if ctx.config.payload_mutation_enabled == 0 {
            return (LayerDecision::Continue, None);
        }

        let target = ctx.config.payload_mutation_target;
        let applies_direction = match (target, ctx.direction) {
            (x, _) if x == MutationTarget::Both as u64 => true,
            (x, Some(Direction::Uplink)) if x == MutationTarget::UplinkOnly as u64 => true,
            (x, Some(Direction::Downlink)) if x == MutationTarget::DownlinkOnly as u64 => true,
            _ => false,
        };
        if !applies_direction {
            return (LayerDecision::Continue, None);
        }

        if ctx.config.payload_mutation_every_n_packets > 1 {
            let n = ctx.config.payload_mutation_every_n_packets;
            if !ctx.now_ns.is_multiple_of(n) {
                return (LayerDecision::Continue, None);
            }
        }

        let size = buffer.len() as u64;
        let min_size = ctx.config.payload_mutation_min_size;
        let max_size = ctx.config.payload_mutation_max_size;
        if (min_size > 0 && size < min_size) || (max_size > 0 && size > max_size) {
            return (LayerDecision::Continue, None);
        }

        if ctx.config.payload_mutation_prob_ppm < 1_000_000 {
            let probe = lcg64(
                ctx.config.policy_seed
                    ^ ctx.config.payload_mutation_corrupt_seed
                    ^ ctx.now_ns
                    ^ ctx.bytes,
            ) % 1_000_000;
            if probe >= ctx.config.payload_mutation_prob_ppm {
                return (LayerDecision::Continue, None);
            }
        }

        let kind = ctx.config.payload_mutation_type;
        let mutation = match kind {
            x if x == MutationKind::Truncate as u64 => Mutation::Truncate {
                size: ctx.config.payload_mutation_truncate_size,
            },
            x if x == MutationKind::CorruptBytes as u64 => Mutation::CorruptBytes {
                count: ctx.config.payload_mutation_corrupt_count,
                seed: ctx.config.payload_mutation_corrupt_seed,
            },
            x if x == MutationKind::InjectBytes as u64 => Mutation::InjectBytes {
                position: ctx.config.payload_mutation_inject_position,
                data: ctx.config.payload_mutation_inject_data,
                len: ctx.config.payload_mutation_inject_len,
            },
            x if x == MutationKind::ReplacePattern as u64 => Mutation::ReplacePattern {
                find: ctx.config.payload_mutation_replace_find,
                find_len: ctx.config.payload_mutation_replace_find_len,
                replace: ctx.config.payload_mutation_replace_with,
                replace_len: ctx.config.payload_mutation_replace_with_len,
            },
            x if x == MutationKind::CorruptEncoding as u64 => Mutation::CorruptEncoding,
            x if x == MutationKind::SwapBytes as u64 => Mutation::SwapBytes {
                pos1: ctx.config.payload_mutation_swap_pos1,
                pos2: ctx.config.payload_mutation_swap_pos2,
            },
            _ => return (LayerDecision::Continue, None),
        };

        if ctx.config.payload_mutation_dry_run > 0 {
            return (LayerDecision::Mutate(vec![mutation]), None);
        }

        let max_buffer = ctx.config.payload_mutation_max_buffer_size;
        let out = apply_mutation(buffer, &mutation, max_buffer as usize);
        (LayerDecision::Mutate(vec![mutation]), out)
    }

    fn name(&self) -> &str {
        "L6_Presentation"
    }
}

fn lcg64(seed: u64) -> u64 {
    seed.wrapping_mul(6364136223846793005).wrapping_add(1)
}

fn apply_mutation(buffer: &[u8], mutation: &Mutation, max_buffer: usize) -> Option<Vec<u8>> {
    let mut out = buffer.to_vec();
    match mutation {
        Mutation::Truncate { size } => {
            let size = *size as usize;
            if size >= out.len() {
                return None;
            }
            out.truncate(size);
        }
        Mutation::CorruptBytes { count, seed } => {
            if out.is_empty() || *count == 0 {
                return None;
            }
            let mut state = lcg64(*seed);
            for _ in 0..*count {
                state = lcg64(state);
                let idx = (state as usize) % out.len();
                state = lcg64(state);
                out[idx] ^= (state & 0xFF) as u8;
            }
        }
        Mutation::InjectBytes {
            position,
            data,
            len,
        } => {
            let position = *position as usize;
            let len = (*len as usize).min(data.len());
            if position > out.len() || len == 0 {
                return None;
            }
            if out.len().saturating_add(len) > max_buffer {
                return None;
            }
            out.splice(position..position, data[..len].iter().copied());
        }
        Mutation::ReplacePattern {
            find,
            find_len,
            replace,
            replace_len,
        } => {
            let find_len = (*find_len as usize).min(find.len());
            let replace_len = (*replace_len as usize).min(replace.len());
            if find_len == 0 {
                return None;
            }
            let needle = &find[..find_len];
            if let Some(pos) = out.windows(find_len).position(|w| w == needle) {
                let mut next = Vec::with_capacity(out.len() + replace_len.saturating_sub(find_len));
                next.extend_from_slice(&out[..pos]);
                next.extend_from_slice(&replace[..replace_len]);
                next.extend_from_slice(&out[pos + find_len..]);
                if next.len() > max_buffer {
                    return None;
                }
                out = next;
            } else {
                return None;
            }
        }
        Mutation::CorruptEncoding => {
            if out.is_empty() {
                return None;
            }
            out[0] = 0xFF;
        }
        Mutation::SwapBytes { pos1, pos2 } => {
            let pos1 = *pos1 as usize;
            let pos2 = *pos2 as usize;
            if pos1 >= out.len() || pos2 >= out.len() || pos1 == pos2 {
                return None;
            }
            out.swap(pos1, pos2);
        }
    }

    if out.len() > max_buffer {
        return None;
    }
    if out == buffer {
        return None;
    }
    Some(out)
}
