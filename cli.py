#!/usr/bin/env python3
"""Command-line interface for Royal Kludge M87."""

import argparse
import sys

from rkm87.audio import MUSIC_STYLES, MusicVisualizerController
from rkm87.daemon import start_daemon
from rkm87.device import RKDevice
from rkm87.lighting import LightingConfig, LightingManager, load_modes_data
from rkm87.screen import ScreenUploader


def cmd_list(args):
    data = load_modes_data()
    print("=== Built-in Lighting Modes ===")
    for m in data.get("modes", []):
        print(f"  [{m['id']:2d}] {m['name']}")

    print("\n=== Palette Colors ===")
    for p in data.get("palette", []):
        print(f"  [{p['id']}] {p['name']}")


def cmd_status(args):
    with RKDevice() as dev:
        if not dev.fd:
            print("Error: Could not find or open RK M87 keyboard.")
            sys.exit(1)
        mode_str = "2.4GHz Dongle" if dev.is_dongle else "USB Cable"
        print(f"Device: {dev.dev_path} ({mode_str})")

        mgr = LightingManager(dev)
        cfg = mgr.get_current_lighting()
        if cfg is None:
            if dev.is_dongle and not dev.is_awake():
                print("Status: Keyboard is currently in wireless sleep mode. Press any key to wake it.")
            else:
                print("Status: Could not read hardware lighting state.")
            return

        mode_name = mgr.get_mode_name(cfg.effect)
        color_name = "Custom / Palette " + str(cfg.palette_index)
        for p in mgr.palette:
            if p["id"] == cfg.palette_index:
                color_name = p["name"]
                break

        deb_str = "Gaming Mode (1ms)" if cfg.debounce == 1 else "Office Mode (4ms)"
        sleep_str = f"{cfg.sleep_minutes} minutes" if cfg.sleep_minutes > 0 else "Never (Always On)"

        print(f"Active Hardware State:")
        print(f"  Mode:       [{cfg.effect}] {mode_name}")
        print(f"  Brightness: {cfg.brightness} / 20")
        print(f"  Speed:      {cfg.speed} / 4")
        print(f"  Color:      {color_name}")
        print(f"  Debounce:   {deb_str}")
        print(f"  Sleep Time: {sleep_str}")



def cmd_sync(args):
    with RKDevice() as dev:
        if not dev.fd:
            print("Error: Could not find or open RK M87 keyboard.")
            sys.exit(1)
        mode_str = "2.4GHz Dongle" if dev.is_dongle else "USB Cable"
        print(f"Connected to RK M87 on {dev.dev_path} ({mode_str})")

        from rkm87.audio import get_current_volume
        from datetime import datetime

        vol = get_current_volume()
        now = datetime.now()
        print(f"Syncing Time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Syncing Volume: {vol}%")

        ok = dev.sync_time_and_volume(vol, now)
        if ok:
            print("Success: Time and volume synchronized to keyboard LCD!")
        else:
            print("Failed to sync (keyboard may be asleep).")


def cmd_mode(args):
    with RKDevice() as dev:
        if not dev.fd:
            print("Error: Could not find or open RK M87 keyboard.")
            sys.exit(1)

        mgr = LightingManager(dev)

        # Parse effect
        effect_id = 1
        if args.mode.isdigit():
            effect_id = int(args.mode)
        else:
            for m in mgr.modes:
                if args.mode.lower() in m["name"].lower():
                    effect_id = m["id"]
                    break

        # If user picked Off or 0, force brightness to 0
        brightness = args.brightness
        if effect_id == 0 or args.mode.lower() in ["off", "none", "0"]:
            effect_id = 0
            brightness = 0

        # Parse palette or custom hex
        palette_id = 7  # default rainbow
        custom_rgb = None
        if args.hex:
            hex_str = args.hex.lstrip("#")
            if len(hex_str) == 6:
                try:
                    custom_rgb = (
                        int(hex_str[0:2], 16),
                        int(hex_str[2:4], 16),
                        int(hex_str[4:6], 16),
                    )
                    palette_id = 0
                except ValueError:
                    print(f"Warning: Invalid hex color '{args.hex}', using palette default.")
        elif args.color:
            if args.color.isdigit():
                palette_id = int(args.color)
            else:
                for p in mgr.palette:
                    if args.color.lower() in p["name"].lower():
                        palette_id = p["id"]
                        break

        cfg = LightingConfig(
            effect=effect_id,
            brightness=brightness,
            speed=args.speed,
            palette_index=palette_id
        )

        mode_name = mgr.get_mode_name(effect_id)
        color_desc = f"Hex #{custom_rgb[0]:02X}{custom_rgb[1]:02X}{custom_rgb[2]:02X}" if custom_rgb else f"Palette {palette_id}"
        print(f"Setting Lighting: {mode_name} | Brightness: {cfg.brightness} | Speed: {cfg.speed} | Color: {color_desc}")
        ok = mgr.set_lighting(cfg, custom_rgb=custom_rgb)
        if ok:
            print("Lighting updated successfully!")
        else:
            print("Failed to update lighting (keyboard might be asleep).")


def cmd_upload(args):
    with RKDevice() as dev:
        if not dev.fd:
            print("Error: Could not find or open RK M87 keyboard.")
            sys.exit(1)

        if dev.is_dongle:
            print("Error: Screen image/GIF uploads are only supported over USB Cable.")
            print("Please plug the keyboard in using the USB-C cable and switch it to wired mode.")
            sys.exit(1)

        uploader = ScreenUploader(dev)

        def progress(step, total, text):
            pct = int((step / total) * 100) if total > 0 else 0
            bar_len = 30
            filled = int((pct / 100.0) * bar_len)
            bar = "█" * filled + "░" * (bar_len - filled)
            sys.stdout.write(f"\r[{bar}] {pct:3d}% - {text}    ")
            sys.stdout.flush()

        print(f"Starting upload for: {args.file}")
        try:
            uploader.upload_gif(args.file, progress_callback=progress)
            print("\n✓ Upload complete! The animation is now active on your keyboard screen.")
        except KeyboardInterrupt:
            print("\n⚠️ Upload interrupted! Aborting and resetting screen display safely...")
            uploader.abort()
            print("Screen reset complete.")
        except Exception as e:
            print(f"\n❌ Upload failed: {e}")


def cmd_daemon(args):
    start_daemon(music=args.music)


def cmd_custom(args):
    with RKDevice() as dev:
        if not dev.fd:
            print("Error: Could not find or open RK M87 keyboard.")
            sys.exit(1)

        mgr = LightingManager(dev)
        if not args.profile:
            profiles = mgr.list_custom_profiles()
            print("Available Custom Lighting Profiles:")
            for p in profiles:
                print(f"  - {p}")
            return

        prof_data = mgr.load_custom_profile(args.profile)
        if not prof_data:
            print(f"Error: Profile '{args.profile}' not found in data/custom_profiles/.")
            sys.exit(1)

        keys_map = prof_data.get("keys", {})
        print(f"Applying Custom Profile: '{prof_data.get('name', args.profile)}' ({len(keys_map)} keys mapped, Brightness: {args.brightness})")
        ok = mgr.set_custom_matrix_lighting(keys_map, brightness=args.brightness)
        if ok:
            print("Custom lighting profile applied successfully!")
        else:
            print("Failed to apply custom lighting (keyboard might be asleep).")


def cmd_music(args):
    with RKDevice() as dev:
        if not dev.fd:
            print("Error: Could not find or open RK M87 keyboard.")
            sys.exit(1)

        if dev.is_dongle:
            print("Error: Real-time keyboard LED music visualizer is disabled in 2.4GHz Dongle mode (firmware limitation).")
            print("Please plug the keyboard in using the USB-C cable and switch it to wired mode.")
            sys.exit(1)

        style_info = MUSIC_STYLES.get(args.style, MUSIC_STYLES[1])
        print(f"Starting Live Music Visualizer: [{args.style}] {style_info['name']}")
        print(f"Gain: {args.gain}x | Press Ctrl+C to stop.\n")

        ctrl = MusicVisualizerController(dev)
        ctrl.start(style_id=args.style, gain=args.gain)

        import time
        try:
            while True:
                time.sleep(0.1)
                if ctrl.streamer:
                    levels = ctrl.streamer.smooth_levels
                    meter = "".join([" ▂▃▄▅▆▇█"[min(7, int(v * 8))] for v in levels])
                    sys.stdout.write(f"\rEQ: [{meter}]")
                    sys.stdout.flush()
        except KeyboardInterrupt:
            print("\nStopping music visualizer...")
        finally:
            ctrl.stop()
            print("Music visualizer stopped and lighting restored.")


def cmd_debounce(args):
    with RKDevice() as dev:
        if not dev.fd:
            print("Error: Could not find or open RK M87 keyboard.")
            sys.exit(1)
        mgr = LightingManager(dev)
        val = 1 if args.mode.lower() in ("1", "gaming", "game") else 4
        mode_str = "Gaming Mode (1ms)" if val == 1 else "Office Mode (4ms)"
        cfg = mgr.get_current_lighting() or LightingConfig()
        cfg.debounce = val
        if mgr.set_lighting(cfg):
            print(f"✓ Debounce updated to: {mode_str}")
        else:
            print("❌ Failed to update debounce (keyboard may be asleep).")


def cmd_sleep(args):
    with RKDevice() as dev:
        if not dev.fd:
            print("Error: Could not find or open RK M87 keyboard.")
            sys.exit(1)
        mgr = LightingManager(dev)
        minutes = int(args.minutes)
        if minutes == 0:
            print("⚠️ WARNING: Setting wireless sleep to 'Never' keeps the keyboard powered indefinitely.")
            print("If unplugged, battery will drain to 0%, which can permanently damage lithium cells.")
        cfg = mgr.get_current_lighting() or LightingConfig()
        cfg.sleep_minutes = minutes
        if mgr.set_lighting(cfg):
            sleep_desc = f"{minutes} minutes" if minutes > 0 else "Never (Always On)"
            print(f"✓ Wireless sleep timeout updated to: {sleep_desc}")
        else:
            print("❌ Failed to update sleep timeout (keyboard may be asleep).")


def cmd_reset(args):
    with RKDevice() as dev:
        if not dev.fd:
            print("Error: Could not find or open RK M87 keyboard.")
            sys.exit(1)
        from rkm87.keymap import KeyMappingManager
        keymap_mgr = KeyMappingManager(dev)
        mgr = LightingManager(dev)
        if not args.yes:
            ans = input("Are you sure you want to reset all keyboard data to factory defaults? [y/N]: ")
            if ans.lower() not in ("y", "yes"):
                print("Reset cancelled.")
                return
        print("Resetting on-device keymaps, lighting profile, and color tables...")
        if mgr.reset_keyboard_data(keymap_mgr=keymap_mgr):
            print("✓ All keyboard data successfully reset to clean factory defaults!")
        else:
            print("❌ Failed to reset keyboard data (keyboard may be asleep).")


def main():
    parser = argparse.ArgumentParser(description="Royal Kludge M87 Native Linux Driver CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    subparsers.add_parser("list", help="List predefined lighting modes and palette colors")

    # status
    subparsers.add_parser("status", help="Read current active hardware lighting state")

    # sync
    subparsers.add_parser("sync", help="Synchronize current system time and volume to keyboard screen")


    # mode
    p_mode = subparsers.add_parser("mode", help="Change RGB lighting mode")
    p_mode.add_argument("mode", help="Mode number (1-21) or mode name (e.g. 'Breathing')")
    p_mode.add_argument("-b", "--brightness", type=int, default=20, choices=[0, 4, 8, 12, 16, 20], help="Brightness (0-20)")
    p_mode.add_argument("-s", "--speed", type=int, default=2, choices=[0, 1, 2, 3, 4], help="Speed (0-4)")
    p_mode.add_argument("-c", "--color", help="Color name (Red, Green, Blue, etc.) or palette ID (0-7)")
    p_mode.add_argument("-x", "--hex", help="Custom hex RGB color (e.g. '#FF3388')")

    # upload
    p_upload = subparsers.add_parser("upload", help="Upload image or animated GIF to keyboard screen (Wired mode)")
    p_upload.add_argument("file", help="Path to GIF or image file")

    # custom
    p_custom = subparsers.add_parser("custom", help="Apply custom per-key RGB lighting profile")
    p_custom.add_argument("profile", nargs="?", help="Profile name (e.g. 'wasd_gaming', 'fps_arena', etc.)")
    p_custom.add_argument("-b", "--brightness", type=int, default=20, choices=[0, 4, 8, 12, 16, 20], help="Brightness (0-20)")

    # music
    p_music = subparsers.add_parser("music", help="Live Winamp-style audio spectrum RGB visualizer")
    p_music.add_argument("-s", "--style", type=int, default=1, choices=list(MUSIC_STYLES.keys()), help="Visualizer style (1-10)")
    p_music.add_argument("-g", "--gain", type=float, default=1.2, help="Audio input sensitivity gain (default 1.2)")

    # debounce
    p_deb = subparsers.add_parser("debounce", help="Set hardware key debounce filter (Gaming 1ms vs Office 4ms)")
    p_deb.add_argument("mode", choices=["gaming", "office", "1", "4"], help="Debounce mode: 'gaming' (1ms) or 'office' (4ms)")

    # sleep
    p_sleep = subparsers.add_parser("sleep", help="Set wireless inactivity sleep timeout (minutes)")
    p_sleep.add_argument("minutes", type=int, choices=[0, 10, 20, 40, 60], help="Minutes before entering sleep (0 = Never / Always On)")

    # reset
    p_reset = subparsers.add_parser("reset", help="Reset all on-device keymaps, lighting, and color tables to factory defaults")
    p_reset.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")

    # daemon
    p_daemon = subparsers.add_parser("daemon", help="Run background synchronization daemon")
    p_daemon.add_argument("--music", action="store_true", help="Enable live audio/music RGB visualizer")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "sync":
        cmd_sync(args)
    elif args.command == "mode":
        cmd_mode(args)
    elif args.command == "custom":
        cmd_custom(args)
    elif args.command == "music":
        cmd_music(args)
    elif args.command == "upload":
        cmd_upload(args)
    elif args.command == "debounce":
        cmd_debounce(args)
    elif args.command == "sleep":
        cmd_sleep(args)
    elif args.command == "reset":
        cmd_reset(args)
    elif args.command == "daemon":
        cmd_daemon(args)


if __name__ == "__main__":
    main()
