const std=@import("std");
pub fn build(b:*std.Build) void {
 const target=b.standardTargetOptions(.{.default_target=.{.cpu_arch=.x86_64,.os_tag=.windows,.abi=.gnu}});const opt=b.standardOptimizeOption(.{});
 const m=b.createModule(.{.root_source_file=b.path("main.zig"),.target=target,.optimize=opt,.link_libc=true});m.addIncludePath(b.path("."));
 for([_][]const u8{"um","shared","ucrt"}) |p|m.addSystemIncludePath(.{.cwd_relative=b.fmt("C:/Program Files (x86)/Windows Kits/10/Include/10.0.26100.0/{s}",.{p})});
 for([_][]const u8{"d3d12","dxgi","dxguid","kernel32"}) |lib|m.linkSystemLibrary(lib,.{});
 m.addCSourceFile(.{.file=b.path("runtime.c"),.flags=&.{"-O2"}});b.installArtifact(b.addExecutable(.{.name="storage",.root_module=m}));
 const t=b.addTest(.{.root_module=b.createModule(.{.root_source_file=b.path("tests.zig"),.target=target,.optimize=opt})});b.step("test","Storage contracts").dependOn(&b.addRunArtifact(t).step);
}
