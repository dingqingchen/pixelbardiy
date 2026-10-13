namespace HaloStudio;

public sealed partial class StudioForm
{
    public void AuditInputs(string output)
    {
        if (!previewMode) throw new InvalidOperationException("Input audit requires preview");
        var saved = current; var results = new List<string>();
        void Check(bool good, string name) { if (!good) throw new InvalidOperationException(name); results.Add(name); }
        IEnumerable<Control> Descendants(Control c) => c.Controls.Cast<Control>().SelectMany(x => new[] { x }.Concat(Descendants(x)));
        try
        {
            SelectPage(2); Activate(); var number = Descendants(this).OfType<CommitNumber>().Single(n => n.AccessibleName == "时间轴偏移");
            var editor = number.Controls.OfType<TextBox>().Single();
            void Type(string value) { Check(editor.Focus(), $"Editor takes focus (visible={editor.Visible}, enabled={editor.Enabled}, canfocus={editor.CanFocus}, formvisible={Visible})"); editor.Text = value; }
            Type("2.3");
            var blank = Message.Create(heading.Handle, 0x201, IntPtr.Zero, IntPtr.Zero); inputCommit.PreFilterMessage(ref blank);
            Check(current.Offset == 2.3 && engine.Config.Offset == 2.3 && !number.ContainsFocus, "Blank click commits typed numeric value and removes caret");
            Check(Files.Load<Settings>(Path.Combine(runtime, "settings.json"))?.Offset == 2.3, "Committed value is persisted immediately");
            Type("-1.7");
            var enter = Message.Create(number.Handle, 0x100, (IntPtr)Keys.Enter, IntPtr.Zero);
            bool entered = inputCommit.PreFilterMessage(ref enter);
            Check(entered && current.Offset == -1.7 && !number.ContainsFocus, $"Enter commits negative decimal and ends edit (handled={entered}, value={current.Offset}, focus={number.ContainsFocus}, text={number.Text}, active={ActiveControl?.GetType().Name})");
            Type("999"); inputCommit.Commit(); Check(current.Offset == 30 && number.Text == "30.0", "Out-of-range input clamps and displays committed value");
            Type("-"); inputCommit.Commit(); Check(current.Offset == 30 && number.Text == "30.0", "Incomplete input restores last valid value");
            Type("1.4"); Set(current with { Rhythm = !current.Rhythm }); Check(number.Text == "1.4", "Other setting changes do not overwrite active input"); inputCommit.Commit();
            SelectPage(1); fanKey.Focus(); fanKey.Text = "audit_fan"; fanMax.Text = "2800"; inputCommit.Commit();
            Check(current.FanLimits.GetValueOrDefault("audit_fan") == 2800 && !fanKey.ContainsFocus, "Valid fan pair applies on blank click without save button");
            Files.Save(output, new { Passed = true, Count = results.Count, Checks = results });
        }
        catch (Exception e) { Files.Save(output, new { Passed = false, Error = e.ToString(), Checks = results }); }
        finally { Set(saved); }
    }
}
