namespace HaloStudio;

public sealed partial class StudioForm
{
    // Offline-only diagnostic: exercise resize reflow in one process, including
    // returning to the wide layout after narrowing it. Never touches the device.
    public void AuditLayout(string directory)
    {
        if (!previewMode) throw new InvalidOperationException("Layout audit requires --preview");
        Directory.CreateDirectory(directory); var evidence = new List<object>(); var failures = new List<string>();
        auditing = true;
        // Reloading used to create unscaled chips at 150% DPI, clipping labels.
        var startupSwatches = swatches.Select(c => (c.Hex, c.Size, c.Margin)).ToArray();
        for (int reload = 0; reload < 3; reload++)
        {
            ReloadColors(); PerformLayout(); Application.DoEvents();
            if (!swatches.Select(c => (c.Hex, c.Size, c.Margin)).SequenceEqual(startupSwatches)) failures.Add("Palette reload changes swatch size or order");
            foreach (var chip in swatches)
                if (chip.Height - Palette.Px(chip, 43) < TextRenderer.MeasureText(chip.Text, chip.Font).Height) failures.Add("Palette label clipped after reload: " + chip.Text);
        }
        var sample = Showcase.Sample(0);
        var savedColors = current;
        try
        {
            ApplyTestSettings(current with { Themes = true, ScreenWhiteBlue = 144 });
            swatches.Single(c => c.Official && c.Hex == "#FFFFFF").PerformClick();
            if (current.DeviceScreenColor() != "#FFFFFF" || !current.OfficialScreenColor() || swatches.Count(c => c.Selected) != 1) failures.Add("Official white selection or source highlight mismatch");
            swatches.Single(c => !c.Official && c.Hex == "#FFFFFF").PerformClick();
            if (current.DeviceScreenColor() != "#FFFF90" || current.OfficialScreenColor() || swatches.Count(c => c.Selected) != 1) failures.Add("Calibrated white selection or source highlight mismatch");
        }
        finally { ApplyTestSettings(savedColors); }
        var manySensors = new Snapshot(sample.Metrics.Concat(Enumerable.Range(0, 32).Select(i => new Metric("extra_" + i, "扩展传感器 " + (i + 1), "EXTRA", i, "%", "离线布局测试", 100))).ToArray(), "offline scroll fixture");
        foreach (int logicalWidth in new[] { 1280, 1020, 1520, 1920, 1020, 1280 })
        {
            ClientSize = new(Palette.Px(this, logicalWidth), Palette.Px(this, 900));
            for (int page = 0; page < 5; page++)
            {
                SelectPage(page); pages[page].AutoScrollPosition = Point.Empty; PerformLayout(); Application.DoEvents();
                if (page == 1) { UpdateSensors(manySensors); Application.DoEvents(); }
                if (pages[page].HorizontalScroll.Visible) failures.Add($"{logicalWidth}/{page}: unexpected horizontal scroll");
                if (preview.Viewport.Width < preview.Width * .85 || preview.Viewport.Width != preview.Viewport.Height * 8) failures.Add($"{logicalWidth}: preview too small or distorted");
                foreach (var button in navigation) if (button.Right > button.Parent!.ClientSize.Width || button.Left < 0) failures.Add($"{logicalWidth}: clipped sidebar button");
                var footer = sidebarStatus.Parent!;
                if (footer.Controls.Cast<Control>().Max(c => c.Bottom + c.Margin.Bottom) > footer.Height + 2 || footer.Height - footer.Controls.Cast<Control>().Max(c => c.Bottom + c.Margin.Bottom) > Palette.Px(this, 8)) failures.Add($"{logicalWidth}: sidebar footer has clipping or excessive bottom space");
                var cards = pages[page].Controls.Cast<Control>().ToArray();
                for (int i = 0; i < cards.Length; i++) for (int j = i+1; j < cards.Length; j++) if (cards[i].Bounds.IntersectsWith(cards[j].Bounds)) failures.Add($"{logicalWidth}/{page}: overlapping cards");
                var columnBottoms = new Dictionary<int, int>(); int baseline = pages[page].Padding.Top;
                foreach (var card in cards)
                {
                    if (card is StudioCard { FullWidth: false })
                    {
                        int expected = columnBottoms.GetValueOrDefault(card.Left, baseline);
                        if (Math.Abs(card.Top - expected) > 2) failures.Add($"{logicalWidth}/{page}: avoidable gap above {card.AccessibleName}");
                        columnBottoms[card.Left] = card.Bottom + Palette.Px(this, 18);
                    }
                    else { baseline = card.Bottom + Palette.Px(this, 18); columnBottoms.Clear(); }
                }
                if (page == 1 && cards[^1].AccessibleName != "实时硬件状态") failures.Add("Hardware table is not last");
                if (page == 1)
                {
                    var metricCard = cards.First(c => c.AccessibleName == "显示指标");
                    if (metricCard.Height > Palette.Px(this, 480) + 2) failures.Add($"{logicalWidth}: metric card exceeds maximum height");
                    if (!metrics.VerticalScroll.Visible || metrics.HorizontalScroll.Visible) failures.Add($"{logicalWidth}: metric viewport scrollbar mismatch");
                    var selectedBefore = metrics.SelectedKeys;
                    metrics.AutoScrollPosition = new Point(0, metrics.DisplayRectangle.Height); Application.DoEvents();
                    var lastChip = metrics.Controls[^1];
                    if (lastChip.Bottom > metrics.ClientSize.Height + 2 || lastChip.Top < 0) failures.Add($"{logicalWidth}: last metric cannot be scrolled into view");
                    int scrollBefore = metrics.AutoScrollPosition.Y; metrics.Update(manySensors, []);
                    if (metrics.AutoScrollPosition.Y != scrollBefore || !metrics.SelectedKeys.SequenceEqual(selectedBefore)) failures.Add($"{logicalWidth}: sensor refresh resets scroll or pending selection");
                    var applyButton = metricCard.Controls[0].Controls.OfType<ModernButton>().First();
                    if (applyButton.Bottom > metricCard.Controls[0].Height) failures.Add($"{logicalWidth}: metrics apply button outside fixed card");
                    metrics.AutoScrollPosition = Point.Empty;
                }
                foreach (Control card in pages[page].Controls)
                {
                    if (card is StudioCard && card.Controls.Count > 0)
                    {
                        var content = card.Controls[0];
                        if (content.Height < 20 || content.Bottom > card.Height - card.Padding.Bottom + 2) failures.Add($"{logicalWidth}/{page}: clipped or empty card");
                        foreach (Control item in content.Controls)
                        {
                            if (item.Right > content.Width + 2) failures.Add($"{logicalWidth}/{page}: horizontal overflow {item.GetType().Name}");
                            if (item is SettingRow) foreach (Control field in item.Controls) if (field.Right > item.Width+2 || field.Bottom > item.Height+2) failures.Add($"{logicalWidth}/{page}: clipped setting {field.Text}");
                        }
                    }
                }
                if (page == 0)
                {
                    var paletteCard = officialChips.Parent!.Parent!;
                    foreach (var chip in officialChips.Controls.Cast<Control>())
                        if (chip.Right > officialChips.ClientSize.Width || chip.Bottom > officialChips.ClientSize.Height) failures.Add($"{logicalWidth}: official color clipped {chip.Text}");
                    using (var bitmap = new Bitmap(paletteCard.Width, paletteCard.Height))
                    {
                        paletteCard.DrawToBitmap(bitmap, new(Point.Empty, bitmap.Size));
                        bitmap.Save(Path.Combine(directory, $"{logicalWidth}-official-palette.png"));
                    }
                    for (int i = 0; i < tiles.Count; i++)
                    {
                        if (tiles[i].Right > gallery.Width || tiles[i].Bottom > gallery.Height) failures.Add($"{logicalWidth}: tile outside gallery");
                        for (int j = i+1; j < tiles.Count; j++) if (tiles[i].Bounds.IntersectsWith(tiles[j].Bounds)) failures.Add($"{logicalWidth}: overlapping tiles");
                    }
                }
                string name = $"{evidence.Count:00}-{logicalWidth}-page{page}";
                SaveScreenshot(Path.Combine(directory, name + ".png"));
                evidence.Add(new { Width = logicalWidth, Dpi = DeviceDpi, Page = page, Columns = pages[page].Columns, Preview = preview.Viewport, Client = pages[page].ClientRectangle, Display = pages[page].DisplayRectangle, HScroll = pages[page].HorizontalScroll.Visible, Cards = pages[page].Controls.Cast<Control>().Select(c => c.Bounds).ToArray(), Gallery = gallery.Size, Tiles = tiles.Select(t => t.Bounds).ToArray() });
                if (page == 1)
                {
                    var metricCard = cards.First(c => c.AccessibleName == "显示指标");
                    using var bitmap = new Bitmap(metricCard.Width, metricCard.Height); metricCard.DrawToBitmap(bitmap, new(Point.Empty, bitmap.Size)); bitmap.Save(Path.Combine(directory, name + "-metric-card.png"));
                    metrics.AutoScrollPosition = new Point(0, metrics.DisplayRectangle.Height); Application.DoEvents(); metricCard.DrawToBitmap(bitmap, new(Point.Empty, bitmap.Size)); bitmap.Save(Path.Combine(directory, name + "-metric-card-scrolled.png")); metrics.AutoScrollPosition = Point.Empty;
                    pages[page].AutoScrollPosition = new Point(0, pages[page].DisplayRectangle.Height); Application.DoEvents(); SaveScreenshot(Path.Combine(directory, name + "-bottom.png"));
                }
            }
        }
        // Exercise popup reopening and the Closed-before-Click ordering that
        // previously caused ObjectDisposedException. Only runs in preview mode.
        IEnumerable<Control> Descendants(Control c) => c.Controls.Cast<Control>().SelectMany(child => new[] { child }.Concat(Descendants(child)));
        for (int page = 0; page < pages.Count; page++)
        {
            SelectPage(page); pages[page].AutoScrollPosition = Point.Empty;
            foreach (var combo in Descendants(pages[page]).OfType<StudioCombo>())
            {
                pages[page].ScrollControlIntoView(combo); Application.DoEvents();
                string original = combo.Value; int changes = 0; void Changed(object? _, EventArgs __) => changes++;
                combo.ValueChanged += Changed;
                for (int cycle = 0; cycle < 3; cycle++)
                {
                    combo.PerformClick(); Application.DoEvents();
                    if (combo.Popup.IsDisposed || !combo.Popup.Visible || combo.Popup.Items.Count != combo.Options.Count) failures.Add("Dropdown did not reopen: " + combo.AccessibleName);
                    if (combo.Popup.Width < combo.Width || combo.Popup.Region == null || combo.Popup.Renderer.GetType().Name != "MenuRenderer") failures.Add("Dropdown styling/width mismatch: " + combo.AccessibleName);
                    var currentItem = combo.Popup.Items.Cast<ToolStripMenuItem>().Single(i => i.Checked);
                    if ((string?)currentItem.Tag != original) failures.Add("Dropdown current selection not marked: " + combo.AccessibleName);
                    var other = combo.Popup.Items.Cast<ToolStripMenuItem>().First(i => !i.Checked); string next = (string)other.Tag!;
                    if (page == 1 && cycle == 0)
                    {
                        using var bitmap = new Bitmap(combo.Popup.Width, combo.Popup.Height); combo.Popup.DrawToBitmap(bitmap, new(Point.Empty, bitmap.Size)); bitmap.Save(Path.Combine(directory, "dropdown-" + combo.AccessibleName + ".png"));
                    }
                    combo.Popup.Close(); other.PerformClick();
                    if (combo.Value != next || changes != cycle + 1) failures.Add("Dropdown selection dispatch mismatch: " + combo.AccessibleName);
                    combo.Value = original;
                }
                combo.ValueChanged -= Changed;
            }
        }
        auditing = false;
        Files.Save(Path.Combine(directory, "layout-report.json"), new { Passed = failures.Count == 0, Failures = failures, Evidence = evidence });
    }
}
