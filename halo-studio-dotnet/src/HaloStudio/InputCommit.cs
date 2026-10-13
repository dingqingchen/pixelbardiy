namespace HaloStudio;

// NumericUpDown does not commit typed text until validation; panels and labels
// normally don't take focus, so clicking blank card space never triggers it.
public sealed class CommitNumber : NumericUpDown
{
    public void Commit() { ValidateEditText(); UserEdit = false; Text = Value.ToString("F" + DecimalPlaces, System.Globalization.CultureInfo.CurrentCulture); }
    protected override void OnLeave(EventArgs e) { Commit(); base.OnLeave(e); }
}

sealed class InputCommit(StudioForm form) : IMessageFilter, IDisposable
{
    bool committing;
    public bool PreFilterMessage(ref Message m)
    {
        if (form.IsDisposed) return false;
        bool mouse = m.Msg is 0x201 or 0x204 or 0x207 or 0xA1;
        bool enter = m.Msg == 0x100 && (Keys)m.WParam.ToInt32() == Keys.Enter;
        if (!mouse && !enter) return false;
        var target = Control.FromChildHandle(m.HWnd);
        if (target?.FindForm() != form) return false;
        Control? edit = FindEdit(form);
        if (edit == null || mouse && (target == edit || edit.Contains(target))) return false;
        Commit(); return enter;
    }
    internal static Control? FindEdit(Control parent)
    {
        foreach (Control c in parent.Controls)
        {
            if (!c.ContainsFocus) continue;
            if (c is NumericUpDown or TextBoxBase) return c;
            return FindEdit(c);
        }
        return null;
    }
    public void Commit(bool focus = true)
    {
        if (committing || form.IsDisposed) return;
        committing = true;
        try { if (FindEdit(form) is CommitNumber n) n.Commit(); form.ValidateChildren(); form.ActiveControl = null; if (focus) form.Focus(); }
        finally { committing = false; }
    }
    public void Dispose() => Application.RemoveMessageFilter(this);
}
