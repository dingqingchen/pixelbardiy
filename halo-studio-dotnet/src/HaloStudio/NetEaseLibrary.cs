using System.Runtime.InteropServices;
using System.Text.Json;

namespace HaloStudio;

// Windows ships winsqlite3. Read only the most recently played song's metadata,
// and accept its ID only when both title and artist match the live player.
sealed class NetEaseLibrary
{
    long nextRead; string key = ""; Track? metadata;
    public Track Enrich(Track track)
    {
        if (track.Key != key) { key = track.Key; nextRead = 0; metadata = null; }
        if (Environment.TickCount64 >= nextRead)
        {
            nextRead = Environment.TickCount64 + 3000;
            string path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "NetEase", "CloudMusic", "Library", "webdb.dat");
            metadata = Read(path, track) ?? metadata;
        }
        return metadata == null ? track : track with { SongId = metadata.SongId, Album = metadata.Album, Duration = metadata.Duration };
    }
    internal static Track? Match(string json, Track track)
    {
        using var doc = JsonDocument.Parse(json); var r = doc.RootElement;
        string title = r.GetProperty("name").GetString() ?? "";
        string artist = string.Join("/", r.GetProperty("artists").EnumerateArray().Select(a => a.GetProperty("name").GetString()));
        string id = r.GetProperty("id").ToString();
        if (LyricsStore.Normalize(title) != LyricsStore.Normalize(track.Title) || LyricsStore.Normalize(artist) != LyricsStore.Normalize(track.Artist) || !long.TryParse(id, out long n) || n <= 0) return null;
        double duration = r.GetProperty("duration").GetDouble() / 1000;
        if (!double.IsFinite(duration) || duration <= 0 || track.Duration > 0 && Math.Abs(track.Duration - duration) > 2) return null;
        return track with { SongId = id, Duration = duration, Album = r.GetProperty("album").GetProperty("name").GetString() ?? "" };
    }
    static Track? Read(string path, Track track)
    {
        if (!File.Exists(path)) return null; IntPtr db = IntPtr.Zero, statement = IntPtr.Zero;
        try
        {
            if (Open(path, out db, 1, IntPtr.Zero) != 0) return null; // SQLITE_OPEN_READONLY
            BusyTimeout(db, 25);
            if (Prepare(db, "SELECT jsonStr FROM historyTracks ORDER BY playtime DESC LIMIT 1", -1, out statement, IntPtr.Zero) != 0 || Step(statement) != 100) return null;
            int length = ColumnBytes(statement, 0); if (length <= 0 || length > 262144) return null;
            return Match(Marshal.PtrToStringUTF8(ColumnText(statement, 0), length)!, track);
        }
        catch (Exception e) when (e is JsonException or KeyNotFoundException or InvalidOperationException or DllNotFoundException or EntryPointNotFoundException) { return null; }
        finally { if (statement != IntPtr.Zero) Finalize(statement); if (db != IntPtr.Zero) Close(db); }
    }
    [DllImport("winsqlite3", EntryPoint = "sqlite3_open_v2", CallingConvention = CallingConvention.Cdecl)] static extern int Open([MarshalAs(UnmanagedType.LPUTF8Str)] string file, out IntPtr db, int flags, IntPtr vfs);
    [DllImport("winsqlite3", EntryPoint = "sqlite3_prepare_v2", CallingConvention = CallingConvention.Cdecl)] static extern int Prepare(IntPtr db, [MarshalAs(UnmanagedType.LPUTF8Str)] string sql, int bytes, out IntPtr statement, IntPtr tail);
    [DllImport("winsqlite3", EntryPoint = "sqlite3_step", CallingConvention = CallingConvention.Cdecl)] static extern int Step(IntPtr statement);
    [DllImport("winsqlite3", EntryPoint = "sqlite3_column_text", CallingConvention = CallingConvention.Cdecl)] static extern IntPtr ColumnText(IntPtr statement, int column);
    [DllImport("winsqlite3", EntryPoint = "sqlite3_column_bytes", CallingConvention = CallingConvention.Cdecl)] static extern int ColumnBytes(IntPtr statement, int column);
    [DllImport("winsqlite3", EntryPoint = "sqlite3_busy_timeout", CallingConvention = CallingConvention.Cdecl)] static extern int BusyTimeout(IntPtr db, int ms);
    [DllImport("winsqlite3", EntryPoint = "sqlite3_finalize", CallingConvention = CallingConvention.Cdecl)] static extern int Finalize(IntPtr statement);
    [DllImport("winsqlite3", EntryPoint = "sqlite3_close", CallingConvention = CallingConvention.Cdecl)] static extern int Close(IntPtr db);
}
