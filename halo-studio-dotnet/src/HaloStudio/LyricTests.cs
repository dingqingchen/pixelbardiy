namespace HaloStudio;

static class LyricTests
{
    public static async Task Cache(Action<bool, string> assert, string directory)
    {
        using var store = new LyricsStore(directory); var track = new Track("Cache regression", "Test");
        store.Save(track, "[00:01]Wrong merged version", "Search");
        var exact = track with { SongId = "123" };
        assert((await store.FetchAsync(exact, false, default)).Lines.Count == 0, "Exact song ID cannot reuse title-only cache");
        store.Save(exact, "[00:01]First separate line\n[00:03]Second separate line", "Exact");
        assert((await store.FetchAsync(exact, false, default)).Lines.Count == 2, "Exact version cache retains separate sentences");
        assert((await store.FetchAsync(exact with { SongId = "456" }, false, default)).Lines.Count == 0, "Different song versions use separate caches");
        store.Save(exact, "[00:01]Fallback", "Exact", "[1000,2000](1000,1000,0)Hello (2000,1000,0)world", true);
        var wordCache = await store.FetchAsync(exact, false, default);
        assert(wordCache.Lines[0].Words?.Count == 2 && wordCache.Source.Contains("逐字"), "Word timing survives offline exact-ID cache reload");
        store.Save(exact, "[00:01]Fallback", "Exact", "[1000,2000](0,1000,0)Bad timing", true);
        assert((await store.FetchAsync(exact, false, default)).Lines[0].Text == "Fallback", "Malformed YRC falls back to LRC without losing lyrics");
        store.Save(exact, "[00:01]User override", "本地 LRC");
        assert((await store.FetchAsync(exact, false, default)).Lines[0].Text == "User override", "Explicit local LRC keeps priority");
    }

    public static void Atlas(string path)
    {
        using var bitmap = new Bitmap(1024, Designs.All.Count * 280); using var g = Graphics.FromImage(bitmap); g.Clear(Color.Black); int y = 0;
        foreach (var theme in Designs.All.Keys)
        {
            foreach (double elapsed in new[] { 0.0, 6.0 })
            {
                var frame = Designs.Render("把遥远的星光收进掌心直到黎明照亮最后一个梦", "歌词", new Settings { Theme = theme }, 0, Snapshot.Empty, new(2026, 10, 14), new(elapsed, 6));
                var canvas = new PixelCanvas(); frame.Pixels.CopyTo(canvas.Data, 0);
                using var view = canvas.Bitmap(Color.White, 4); g.DrawImageUnscaled(view, 0, y); y += 136;
            }
            y += 8;
        }
        bitmap.Save(path);
    }

    public static void Run(Action<bool, string> assert)
    {
        List<LyricLine> lines = [new(0, "第一句"), new(5, "第二句"), new(10, "这是一整句很长很长不能切成两页的中文歌词直到最后一个字"), new(20, ""), new(25, "第二句")];
        var player = new LyricPlayback(); var s = new Settings();
        var track = new Track("测试", Duration: 40, Position: 4.3, Playing: true, RealtimeLyric: "第一句");
        assert(player.Select(track, lines, s, 0)?.Text == "第二句", "Default 0.8s lead precedes native current sentence");
        assert(player.Select(track, lines, s with { Offset = -.8 }, .1)?.Text == "第一句", "Negative manual offset delays and cancels lead");
        assert(player.Select(track with { Position = 2.3 }, lines, s with { Offset = 2 }, .2)?.Text == "第二句", "Positive offset advances with native sentence present");
        assert(player.Select(track with { Position = 10 }, lines, s, .3)?.Part == 1 && LyricsStore.At(lines, 18, 40) == lines[2].Text, "Pagination preserves full source line while selecting its timed head");
        assert(player.Select(track with { Position = 20 }, lines, s, .4) == null, "Blank LRC interval clears lyric");
        assert(player.Select(track with { Position = 0 }, lines, s, .5)?.Text == "第一句", "Timeline seek resets selected lyric immediately");
        var background = track with { Provider = "网易云本地进度 · 3.1.41", NativeTimeline = true, RealtimeLyric = "", SongId = "123" };
        assert(new LyricPlayback().Select(background, lines, s, 0)?.Text == "第二句", "Native playback clock syncs immediately without a desktop lyric or observed boundary");
        assert(new LyricPlayback().Select(background with { Position = 2 }, lines, s, 0)?.Text == "第一句", "Backward seek follows true playback clock without lyric window");
        assert(new LyricPlayback().Select(background with { Playing = false }, lines, s, 0) == null, "Native timeline respects paused state");
        assert(NetEaseNative.TimelineProfile(1791636812, 41054208) == (0x21A74D8, 0x2214778) && NetEaseNative.TimelineProfile(0, 41054208) == (0, 0), "Native progress offsets require exact verified PE fingerprint");
        assert(NetEaseNative.ValidTimeline(0, 240) && NetEaseNative.ValidTimeline(239.9, 240) && !NetEaseNative.ValidTimeline(double.NaN, 240) && !NetEaseNative.ValidTimeline(2, 0) && !NetEaseNative.ValidTimeline(500, 240) && !NetEaseNative.ValidTimeline(-1, 240), "Invalid or unavailable native playback clocks are rejected");
        assert(NetEaseNative.IsSongCaption("Song - Artist") && !NetEaseNative.IsSongCaption("MediaPlayer SMTC window - {GUID}") && !NetEaseNative.IsSongCaption("网易云音乐"), "Hidden SMTC helper window cannot replace song title after minimizing");
        List<LyricLine> gapped = [new(0, "上一句"), new(4, ""), new(5, "下一句")];
        assert(new LyricPlayback().Select(track with { Position = 3.5 }, gapped, s, 0)?.Text == "上一句", "Sub-second LRC gaps hold previous sentence without flashing clock");
        var local = track with { Duration = 0, Position = 0, Provider = "网易云本地" }; player = new();
        assert(player.Select(local, lines, s, 100)?.Timed == false, "Native first read does not invent a timeline anchor");
        var unique = local with { RealtimeLyric = lines[2].Text, LineElapsed = 0 };
        assert(player.Select(unique, lines, s, 110)?.Timed == true, "Observed unambiguous native boundary anchors LRC");
        assert(player.Select(unique with { LineElapsed = 8.4 }, lines, s with { Offset = 1 }, 118.4) == null, "Native-only anchor honors lead and manual offset before next boundary");
        assert(player.Select(unique with { Playing = false }, lines, s, 119) == null, "Pause clears extrapolation");
        assert(player.Select(unique, lines, s, 130)?.Timed == false, "Resume waits for fresh boundary instead of including pause duration");
        player = new(); player.Select(local, lines, s, 0);
        assert(player.Select(local with { RealtimeLyric = "第二句" }, lines, s, 1)?.Timed == true, "Repeated choruses allow timing while all candidates agree");
        assert(player.Select(local with { RealtimeLyric = "第二句", LineElapsed = 4.3 }, lines, s, 5.3)?.Timed == false, "Diverging chorus candidates fall back instead of predicting a wrong sentence");
        List<LyricLine> empty = []; player = new(); player.Select(local, empty, s, 0);
        assert(player.Select(local with { RealtimeLyric = "新句" }, empty, s with { Offset = -3 }, 5)?.Text == "第一句", "Current-only fallback can delay previously observed text");
        var meta = NetEaseLibrary.Match("""{"id":"25657274","name":"Talking to the Moon","artists":[{"name":"Bruno Mars"}],"duration":207647,"album":{"name":"Exact album"}}""", new Track("Talking to the Moon", "Bruno Mars"));
        assert(meta?.SongId == "25657274" && meta.Duration == 207.647, "Local metadata matches current title and artist and supplies exact song ID");
        assert(NetEaseLibrary.Match("""{"id":"1","name":"Same title","artists":[{"name":"Other artist"}],"duration":1000,"album":{"name":""}}""", new Track("Same title", "Artist")) == null, "Unrelated latest history entry is rejected");
        assert(!LyricsStore.CanUseTimeline(local, "网易云音乐") && LyricsStore.CanUseTimeline(local with { SongId = "25657274" }, "网易云当前版本") && LyricsStore.CanUseTimeline(local, "本地 LRC"), "Unverified search lyrics cannot override native sentence boundaries");
        List<LyricLine> split = LyricsStore.Parse("[00:24.000]Previous\n[00:27.900]At night when the stars\n[00:31.258]light up my room\n[00:34.640]Next");
        var song = new Track("Talking to the Moon", "Bruno Mars", Duration: 207.647, Position: 27.2, Playing: true, RealtimeLyric: "Previous", SongId: "25657274");
        assert(new LyricPlayback().Select(song, split, new(), 0)?.Key.Contains(":1:page:") == true && new LyricPlayback().Select(song with { Position = 30.5 }, split, new(), 0)?.Key.Contains(":2:page:") == true, "27.900 and 31.258 remain distinct timed sentences with 0.8s lead");
        var mismatch = new LyricPlayback(); mismatch.Select(local, lines, s, 0, false);
        assert(mismatch.Select(local with { RealtimeLyric = "第一句" }, lines, s with { Offset = 20 }, 1, false)?.Text == "第一句", "Wrong-version LRC never replaces native text even with large advance");
        var start = new LyricScroll(0, 6); var end = new LyricScroll(6, 6);
        assert(start.Offset(300) == 0 && end.Offset(300) == 300 && new LyricScroll(100, 6).Offset(300) == 300, "Two endpoint views hold the first and last glyph");
        assert(new LyricScroll(100, 6, .7, null).Progress == 0, "Tail cannot replace head before the head ACK");
        assert(new LyricScroll(0, 1.5, .7, .8).SwitchAt == .8, "Very short intervals submit tail immediately after head ACK");
        foreach (double duration in new[] { 3.0, 4.0, 6.0, 30.0 })
        {
            double transfer = .7, head = .8; var layout = new LyricScroll(0, duration, transfer, head);
            double tailArrives = layout.SwitchAt + transfer;
            assert(duration - tailArrives >= (duration - head) / 2 - .0001, "Tail receives at least half display window after transmission " + duration);
            assert((layout with { Elapsed = layout.SwitchAt - .01 }).Progress == 0 && (layout with { Elapsed = layout.SwitchAt }).Progress == 1, "Endpoint switches directly without intermediate positions " + duration);
        }
        foreach (var theme in Designs.All.Keys)
        {
            s = new Settings { Theme = theme }; var date = new DateTime(2026, 10, 14);
            string text = lines[2].Text;
            var first = Designs.Render(text, "歌词", s, 0, Snapshot.Empty, date, start);
            var mid = Designs.Render(text, "歌词", s, 0, Snapshot.Empty, date, new(.5, 6));
            var last = Designs.Render(text, "歌词", s, 0, Snapshot.Empty, date, end);
            var held = Designs.Render(text, "歌词", s, 0, Snapshot.Empty, date, new(30, 6));
            assert(first.LyricPart == 1 && mid.LyricPart == 1 && last.LyricPart == 2 && first.Pixels.SequenceEqual(mid.Pixels) && !mid.Pixels.SequenceEqual(last.Pixels), theme + " two stable endpoint views, no intermediate scroll frames");
            assert(first.Identity == mid.Identity && first.Text == text && last.Pixels.SequenceEqual(held.Pixels), theme + " endpoint change preserves identity and complete text; no repeated entry animation");
            var rect = Designs.All[theme].Scenes.GetProperty("lyric").EnumerateArray().First(e => e.GetProperty("op").GetString() == "text" && e.GetProperty("text").GetString() == "${text}");
            int x = rect.GetProperty("x").GetInt32(), y = rect.GetProperty("y").GetInt32(), w = rect.GetProperty("w").GetInt32(), h = rect.GetProperty("h").GetInt32();
            bool outsideSame = true;
            for (int yy = 0; yy < 32; yy++) for (int xx = 0; xx < 256; xx++) if (xx < x || xx >= x + w || yy < y || yy >= y + h) { int i = yy / 8 * 256 + xx, bit = 1 << (yy % 8); outsideSame &= (first.Pixels[i] & bit) == (last.Pixels[i] & bit); }
            assert(outsideSame, theme + " scrolling clips to text area and preserves decoration");
            int size = rect.GetProperty("size").GetInt32(), baseline = y + Math.Clamp(h / 2 + size / 3, 0, h - 1);
            bool Lit(PixelFrame f, int xx, int yy) => (f.Pixels[yy / 8 * 256 + xx] & (1 << (yy % 8))) != 0;
            assert(Enumerable.Range(0,3).All(i => Lit(first, x + w - 7 + i * 3, baseline) && Lit(last, x + i * 3, baseline)), theme + " trailing and leading three-dot omission marks");
            assert(Enumerable.Range(y,h).Any(yy => Lit(last, x + w - 1, yy)), theme + " final glyph reaches right edge");
            assert(!Designs.Render("短句", "歌词", s, 0, Snapshot.Empty, date, start).Scrolling, theme + " short lyric stays static");
        }
        WordPages(assert);
    }
    static void WordPages(Action<bool, string> assert)
    {
        var parsed = LyricsStore.ParseYrc("{\"metadata\":true}\n[1000,5000](1000,1000,0)Hello (2000,1000,0)night (3000,1000,0)and (4000,1000,0)stars (5000,1000,0)again\n[6000,1000](6000,1000,0)Next");
        assert(parsed.Count == 2 && parsed[0].Words?.Count == 5 && parsed[0].Words![1].Time == 2 && parsed[0].Text == "Hello night and stars again", "YRC reads absolute word timestamps and preserves spaces and line boundaries");
        foreach (string invalid in new[] { "[1000,2000]missing", "[1000,2000]lost(1000,1000,0)word", "[1000,2000](2000,1000,0)a(1000,1000,0)b", "[1000,2000](1000,5000,0)a", "[1000,2000](0,1000,0)a" })
            assert(LyricsStore.ParseYrc(invalid).Count == 0, "Malformed YRC rejected: " + invalid);
        var chinese = LyricsStore.ParseYrc("[1000,10000]" + string.Concat("让遥远的星光照亮静谧的夜空每一颗星都在诉说故事".Select((ch,i) => $"({1000+i*300},300,0){ch}")))[0];
        foreach (var theme in Designs.All.Keys)
        {
            var settings = new Settings { Theme = theme }; var view = Designs.LyricViewport(settings);
            var pages = LyricPager.Build(chinese, 11, view, .5);
            assert(pages.Length > 1 && string.Concat(pages.Select(p => p.Text)) == chinese.Text && pages.All(p => p.WordTimed && view.Measure(p.Text) <= view.Width), theme + " timed pages fit exact glyph widths and retain every character once");
            int offset = 0;
            foreach (var page in pages) { assert(page.Time == chinese.Words![offset].Time, theme + " page timestamp matches its first character"); offset += page.Text.Length; }
            var playback = new LyricPlayback(); var track = new Track("word test", Duration: 20, Playing: true, NativeTimeline: true);
            List<LyricLine> lines = [chinese, new(11,"结束")]; double boundary = pages[1].Time - settings.LyricLeadSeconds;
            assert(playback.Select(track with { Position = boundary - .02 }, lines, settings, 0)?.Page == 1 && playback.Select(track with { Position = boundary + .02 }, lines, settings, .04)?.Page == 2, theme + " word page uses normal cue clock and 0.8-second lead");
            assert(playback.Select(track with { Position = boundary + .02 }, lines, settings with { Offset = -.8 }, .1)?.Page == 1, theme + " manual offset affects word pages");
            assert(playback.Select(track with { Position = 1 }, lines, settings, .2)?.Page == 1, theme + " backward seek returns to first page");
            assert(playback.Select(track with { Playing = false }, lines, settings, .3) == null, theme + " pause clears timed pages");
            var fallback = new LyricLine(10, chinese.Text); var pager = new LyricPager(); var pair = pager.Pages(fallback, 18, view, .7);
            assert(pair.Length == 2 && pair[0].Text.EndsWith("...") && pair[1].Text.StartsWith("...") && pair.All(p => view.Measure(p.Text) <= view.Width), theme + " untimed long line has exactly two fitting omission pages");
            assert(18 - (pair[1].Time + .7) >= (18 - (10 + .7)) / 2 && ReferenceEquals(pair, pager.Pages(fallback, 18, view, 2)), theme + " tail gets half estimated display time and its timestamp never jitters");
            var first = pager.Select(fallback, 18, view, .7, 10, "test", true); var last = pager.Select(fallback, 18, view, .7, 17, "test", true);
            var a = Designs.Render(first.Text, "歌词", settings, 0, Snapshot.Empty, DateTime.Today, lyricCue: first);
            var b = Designs.Render(last.Text, "歌词", settings, 0, Snapshot.Empty, DateTime.Today, lyricCue: last);
            assert(first.Key != last.Key && a.Identity != b.Identity && !a.Scrolling && !b.Scrolling && !a.Pixels.SequenceEqual(b.Pixels), theme + " fallback pages are distinct normal frame updates, without marquee");
        }
        var narrow = new LyricViewport(70, 28, "body", 20, false);
        var english = LyricPager.Build(parsed[0], 6, narrow, .5);
        assert(english.Length > 1 && english.All(p => p.WordTimed) && string.Join(" ", english.Select(p => p.Text)) == parsed[0].Text, "English wraps at timed word boundaries without merging next source line");
        var indivisible = new LyricLine(0, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", [new(0, 5, "ABCDEFGHIJKLMNOPQRSTUVWXYZ")], 5);
        assert(LyricPager.Build(indivisible, 5, narrow, .5) is { Length: 2 } oversized && oversized.All(p => !p.WordTimed), "Indivisible oversized word falls back instead of inventing timestamps");
    }
}
