// Generated; edit spatial-schema.json. SHA256 4d6d9f2b9239fd45cc042446a8b174db80f765bad5e088166d15c6ca0ff74f4c
#ifndef G2_LAYOUT_H
#define G2_LAYOUT_H
#define G2_VERSION 5u
#define G2_HEADER_BYTES 256u
#define G2_GUARD_BYTES 256u
#define G2_KEY_BYTES 16u
#define G2_HASH_SLOT_BYTES 16u
#define G2_PAIR_BYTES 20u
#define G2_COUNT_BYTES 8u
#define G2_OFFSET_BYTES 8u
#define G2_COVERAGE_BYTES_PER_ENTITY 16u
#define G2_GRAPH_BYTES_PER_ENTITY 12u
#define G2_STICKY_ERROR_BYTE 76u
#define G2_DISPATCH_WIDTH_SHIFT 16u
#define G2_DISPATCH_STAGE_MASK 65535u
#define G2_CELL_EDGE 4u
#define G2_RADIX_BITS 4u
#define G2_THREADS 256u
#define G2_DIMENSIONS 2u
#define G2_DT 1u
#define G2_CONTACT_INDEX_BYTES 4u
#define G2_CONTACT_COUNT_BYTES 8u
#define G2_CONTACT_OFFSET_BYTES 8u
#define G2_CONTACT_TOTAL_BYTE 80u
#define G2_CONTACT_SCAN_FLAG 1024u
#define G2_TAG 0x4d6d9f2bu
#define G2_COUNT(i) (G2_HEADER_BYTES+G2_COUNT_BYTES*(i))
#define G2_OFFSET(cap,i) (G2_HEADER_BYTES+G2_COUNT_BYTES*(cap)+G2_OFFSET_BYTES*(i))
#define G2_COVERAGE(cap,pass,i) (G2_HEADER_BYTES+(G2_COUNT_BYTES+G2_OFFSET_BYTES)*(cap)+4u*((pass)*(cap)+(i)))
#define G2_GRAPH_BASE(cap) (G2_HEADER_BYTES+(G2_COUNT_BYTES+G2_OFFSET_BYTES+G2_COVERAGE_BYTES_PER_ENTITY)*(cap))
#define G2_PARENT(cap,i) (G2_GRAPH_BASE(cap)+4u*(i))
#define G2_SIZE(cap,i) (G2_GRAPH_BASE(cap)+4u*(cap)+4u*(i))
#define G2_DEGREE(cap,i) (G2_GRAPH_BASE(cap)+8u*(cap)+4u*(i))
#define G2_CONTACT_COUNT(cap,i) (G2_GRAPH_BASE(cap)+G2_GRAPH_BYTES_PER_ENTITY*(cap)+G2_CONTACT_COUNT_BYTES*(i))
#define G2_CONTACT_OFFSET(cap,i) (G2_CONTACT_COUNT(cap,cap)+G2_CONTACT_OFFSET_BYTES*(i))
#define G2_SCAN_BASE(cap) (G2_CONTACT_OFFSET(cap,cap))
#endif
