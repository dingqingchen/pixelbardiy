namespace HaloStudio;

internal static class TemperatureDiagnostic
{
    // No USB and no implicit UAC: setup must have been completed separately.
    public static async Task Run(string output)
    {
        using var temperature = new CpuTemperature(); var samples = new List<object>();
        for (int i = 0; i < 12; i++)
        {
            double? value = await temperature.ReadAsync(true, false);
            samples.Add(new { Second = i, Celsius = value, temperature.Detail });
            await Task.Delay(1000);
        }
        Files.Save(output, new { AuthorizedTask = ThermalTask.Ready(), FirmwareWrites = 0, Samples = samples });
    }
}
