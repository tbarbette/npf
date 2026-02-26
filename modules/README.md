# NPF Modules

Modules are reusable `.npf` test fragments that can be included in your test scripts using the `%import` directive. They provide common functionality such as traffic generation, system tuning, device configuration, and performance monitoring.

Usage example:
```
%import graph-beautiful
%import dev_rate
```

## Available Modules

| Module | Description |
|--------|-------------|
| `cpufreq-script` | Set CPU frequency using cpupower, with per-core and variable frequency support |
| `cpuload` | Monitor CPU load by reading `/proc/stat` in a loop, outputting per-core utilization time-series |
| `dev_channels` | Set the number of combined hardware queues (RSS) for a network device via `ethtool -L` |
| `dev_irq_affinity` | Set IRQ affinity for a network device to pin interrupts to specific CPU cores |
| `dev_pause` | Configure Ethernet PAUSE frames (flow control) on a network device via `ethtool -A` |
| `dev_rate` | Measure link rate (bits/s) and packet rate (PPS) of a network device using Linux kernel counters |
| `dpdk-bind` | Bind NICs to UIO driver for DPDK and ensure hugepages are mounted |
| `droptcpsock` | Drop TCP connections in TIME_WAIT state by writing to `/proc/net/tcpdropsock` |
| `fastclick-echo` | Minimal DPDK echo/loopback module using FastClick with EtherMirror |
| `fastclick-play-single-mt` | Generate traffic using FastClick with throughput and latency measurement (UDP or PCAP replay, multi-threaded) |
| `graph-beautiful` | Graph styling module for publication-quality plots (ticks, grid, legend, variable names) |
| `load` | Measure CPU load using mpstat, outputting average CPU load and per-core ratio |
| `netmap-bind` | Insert Netmap kernel module and patched network drivers for packet I/O |
| `nginx` | Launch and configure an NGINX HTTP server with auto-generated `nginx.conf` |
| `perf-class` | Advanced perf profiling using perf-class tool to aggregate symbols into categories |
| `perf-functions` | Simple performance profiling reporting time spent in each function via `perf record/report` |
| `perf-stat` | Collect hardware performance counters (LLC misses, cache, TLB, IPC…) using `perf stat` |
| `pktgen` | Traffic generator using DPDK pktgen with Lua script |
| `snort` | Snort IDS/IPS setup — copies config and installs Snort+DAQ dependencies |
| `trex` | Start the T-Rex traffic generator in stateless mode |
| `waitcon` | Wait until TCP TIME_WAIT connections drop below a threshold, then emit SERVER_CLEAN event |
| `wrk` | Generate HTTP requests using WRK (single instance, basic throughput/latency) |
| `wrk-multins` | HTTP benchmark using WRK across multiple network namespaces |
| `wrk-nsdelay` | Generate HTTP requests using WRK with support for multiple request sizes |
| `wrk2` | Generate HTTP requests using WRK2 with support for increasing rate |
