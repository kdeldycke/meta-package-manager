// TEMPORARY probe helper, deleted with `.github/workflows/hidpi-probe.yaml`.
//
// Creates a display with a 2x backing store through the private
// `CGVirtualDisplay` API, the one DeskPad and FluffyDisplay build on, and keeps
// it up until the process is terminated: the display lives exactly as long as
// the object that created it.
//
//   hidpi_probe WIDTH HEIGHT main|mirror
//
// WIDTH and HEIGHT are in points, and the backing store is twice each. `main`
// puts the new display at the origin and moves the runner's own screen beside
// it; `mirror` turns the runner's screen into a mirror of the new display. A
// line starting with `ready` reports the arrangement once it is in place.
#import <CoreGraphics/CoreGraphics.h>
#import <Foundation/Foundation.h>
#import <signal.h>
#import <unistd.h>

// The private interfaces, as DeskPad's `CGVirtualDisplayPrivate.h` and
// FluffyDisplay's `include/` declare them, and as the ObjC runtime of macOS 26
// lists them.
@interface CGVirtualDisplayDescriptor : NSObject
@property(nonatomic, copy) NSString *name;
@property(nonatomic, strong) dispatch_queue_t queue;
@property(nonatomic) unsigned int maxPixelsWide;
@property(nonatomic) unsigned int maxPixelsHigh;
@property(nonatomic) CGSize sizeInMillimeters;
@property(nonatomic) unsigned int serialNum;
@property(nonatomic) unsigned int productID;
@property(nonatomic) unsigned int vendorID;
@property(nonatomic) CGPoint whitePoint;
@property(nonatomic) CGPoint redPrimary;
@property(nonatomic) CGPoint greenPrimary;
@property(nonatomic) CGPoint bluePrimary;
@end

@interface CGVirtualDisplayMode : NSObject
- (instancetype)initWithWidth:(unsigned int)width
                       height:(unsigned int)height
                  refreshRate:(double)refreshRate;
@end

@interface CGVirtualDisplaySettings : NSObject
@property(nonatomic) unsigned int hiDPI;
@property(nonatomic, strong) NSArray<CGVirtualDisplayMode *> *modes;
@end

@interface CGVirtualDisplay : NSObject
@property(nonatomic, readonly) CGDirectDisplayID displayID;
- (instancetype)initWithDescriptor:(CGVirtualDisplayDescriptor *)descriptor;
- (BOOL)applySettings:(CGVirtualDisplaySettings *)settings;
@end

static volatile sig_atomic_t stopped = 0;

static void on_signal(int signum) {
    (void)signum;
    stopped = 1;
}

// One line per active display: where it sits, its size in points and in
// pixels, and its place in a mirror set.
static void report_displays(const char *label) {
    CGDirectDisplayID ids[8];
    uint32_t count = 0;
    CGGetActiveDisplayList(8, ids, &count);
    printf("%s: main=%u active=%u\n", label, CGMainDisplayID(), count);
    for (uint32_t i = 0; i < count; i++) {
        CGRect bounds = CGDisplayBounds(ids[i]);
        printf("  display %u: origin (%.0f,%.0f) %.0fx%.0f pt, %zux%zu px, "
               "mirrors=%u primary=%u\n",
               ids[i], bounds.origin.x, bounds.origin.y, bounds.size.width,
               bounds.size.height, CGDisplayPixelsWide(ids[i]),
               CGDisplayPixelsHigh(ids[i]), CGDisplayMirrorsDisplay(ids[i]),
               CGDisplayPrimaryDisplay(ids[i]));
    }
    fflush(stdout);
}

int main(int argc, char **argv) {
    if (argc != 4) {
        fprintf(stderr, "usage: %s WIDTH HEIGHT main|mirror\n", argv[0]);
        return 2;
    }
    unsigned int width = (unsigned int)atoi(argv[1]);
    unsigned int height = (unsigned int)atoi(argv[2]);
    BOOL mirror = strcmp(argv[3], "mirror") == 0;
    CGDirectDisplayID original = CGMainDisplayID();
    report_displays("before");

    CGVirtualDisplayDescriptor *descriptor = [CGVirtualDisplayDescriptor new];
    descriptor.name = @"mpm HiDPI probe";
    descriptor.queue = dispatch_queue_create("mpm.hidpi-probe", DISPATCH_QUEUE_SERIAL);
    descriptor.maxPixelsWide = width * 2;
    descriptor.maxPixelsHigh = height * 2;
    // 220 pixels per inch, a Retina panel's density.
    descriptor.sizeInMillimeters =
        CGSizeMake(25.4 * width * 2 / 220.0, 25.4 * height * 2 / 220.0);
    descriptor.serialNum = 1;
    descriptor.productID = 1;
    descriptor.vendorID = 1;
    // sRGB primaries and a D65 white point, as FluffyDisplay declares them.
    descriptor.whitePoint = CGPointMake(0.3125, 0.3291);
    descriptor.redPrimary = CGPointMake(0.6797, 0.3203);
    descriptor.greenPrimary = CGPointMake(0.2559, 0.6983);
    descriptor.bluePrimary = CGPointMake(0.1494, 0.0557);

    // Kept alive to the end of `main`: the display goes away with it.
    __attribute__((objc_precise_lifetime)) CGVirtualDisplay *display =
        [[CGVirtualDisplay alloc] initWithDescriptor:descriptor];
    if (!display) {
        printf("failed: initWithDescriptor returned nil\n");
        return 3;
    }
    CGVirtualDisplaySettings *settings = [CGVirtualDisplaySettings new];
    settings.hiDPI = 1;
    // With `hiDPI` set the mode is declared in points, as FluffyDisplay does
    // when it halves its pixel size.
    settings.modes = @[ [[CGVirtualDisplayMode alloc] initWithWidth:width
                                                             height:height
                                                        refreshRate:60] ];
    if (![display applySettings:settings]) {
        printf("failed: applySettings refused\n");
        return 3;
    }
    CGDirectDisplayID virtual_id = display.displayID;
    printf("created: display %u\n", virtual_id);
    for (int i = 0; i < 100 && !CGDisplayIsActive(virtual_id); i++) {
        usleep(100000);
    }
    report_displays("created");

    CGDisplayConfigRef config = NULL;
    CGBeginDisplayConfiguration(&config);
    CGError configured;
    if (mirror) {
        configured = CGConfigureDisplayMirrorOfDisplay(config, original, virtual_id);
    } else {
        CGConfigureDisplayOrigin(config, virtual_id, 0, 0);
        configured = CGConfigureDisplayOrigin(config, original, (int32_t)width, 0);
    }
    CGError completed = CGCompleteDisplayConfiguration(config, kCGConfigureForSession);
    printf("arranged as %s: configure=%d complete=%d\n", argv[3], configured, completed);
    for (int i = 0; i < 100 && CGMainDisplayID() != virtual_id; i++) {
        usleep(100000);
    }
    report_displays("arranged");
    CGRect bounds = CGDisplayBounds(virtual_id);
    double scale = bounds.size.width > 0 ? CGDisplayPixelsWide(virtual_id) / bounds.size.width : 0;
    printf("ready: main=%u virtual=%u scale=%.1f\n", CGMainDisplayID(), virtual_id, scale);
    fflush(stdout);

    signal(SIGTERM, on_signal);
    signal(SIGINT, on_signal);
    while (!stopped) {
        sleep(1);
    }
    printf("stopped: display %u released\n", display.displayID);
    return 0;
}
