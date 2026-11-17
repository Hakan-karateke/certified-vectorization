// optimal_arcs._arc_steps çekirdeğinin derlenmiş (C#) karşılığı: aynı girdide aynı
// üst küme matrisini üretir. Yalnızca süre karşılaştırması içindir; kitaplığın
// parçası değildir ve tam aritmetik doğrulamayı içermez.
using System;
using System.Diagnostics;
using System.IO;

public static class ArcKernel
{
    const double BetaMax = 0.999, Margin = 1e-6, BetaMargin = 1e-9, LineBeta = 1e-7;

    static double Hypot(double x, double y) { return Math.Sqrt(x * x + y * y); }

    static double ArcDistance(double xi, double eta, double h, double beta)
    {
        double ends = Hypot(Math.Abs(xi) - h, eta);
        if (Math.Abs(beta) < LineBeta) return Math.Abs(xi) <= h ? Math.Abs(eta) : ends;
        double t = h * (beta * beta - 1) / (2 * beta);
        double radius = h * (1 + beta * beta) / (2 * Math.Abs(beta));
        double rho = Hypot(xi, eta - t);
        bool inside = Math.Sign(beta) * (eta - t) * radius >= rho * Math.Abs(t);
        return inside ? Math.Abs(xi * xi + eta * eta - h * h - 2 * eta * t) / (rho + radius) : ends;
    }

    static double Bulge(double x, bool real)
    {
        double b = double.IsInfinity(x) ? Math.Sign(x) : x / (1 + Math.Sqrt(1 + x * x));
        if (!real || double.IsNaN(b) || double.IsInfinity(b)) b = 0.0;
        return Math.Max(-BetaMax, Math.Min(BetaMax, b));
    }

    // p_i → p_{i+d} çifti için verilen ara düğümlerin ortak β aralığı boş değil mi?
    static bool Feasible(double[] pts, int m, int i, int d, int[] offsets, int count, double tol)
    {
        double ax = pts[2 * i], ay = pts[2 * i + 1];
        int j = (i + d) % m;
        double bx = pts[2 * j], by = pts[2 * j + 1];
        double ux = bx - ax, uy = by - ay;
        double length = Hypot(ux, uy);
        if (length <= 0) return false;
        double alx = ux / length, aly = uy / length;
        double rx = aly, ry = -alx;
        double mx = (ax + bx) / 2, my = (ay + by) / 2, h = length / 2;
        double lo = double.NegativeInfinity, hi = double.PositiveInfinity;
        for (int k = 0; k < count; k++)
        {
            int n = (i + offsets[k]) % m;
            double px = pts[2 * n] - mx, py = pts[2 * n + 1] - my;
            double xi = px * alx + py * aly, eta = px * rx + py * ry;
            double plo, phi;
            if (Hypot(Math.Abs(xi) - h, eta) <= tol) { plo = -BetaMax; phi = BetaMax; }
            else
            {
                double big = xi * xi + eta * eta - h * h - tol * tol;
                double qa = big * big - 4 * tol * tol * h * h;
                double half = 2 * big * eta;
                double qc = 4 * (eta * eta - tol * tol);
                double disc = half * half - qa * qc;
                double root = Math.Sqrt(Math.Max(disc, 0.0));
                double q = -(half + (half >= 0 ? root : -root));
                bool real = disc >= 0;
                double b1 = Bulge(q / qa * h, real), b2 = Bulge(qc / q * h, real);
                double first = Math.Min(b1, b2), second = Math.Max(b1, b2);
                bool low = ArcDistance(xi, eta, h, (first - BetaMax) / 2) <= tol;
                bool middle = ArcDistance(xi, eta, h, (first + second) / 2) <= tol;
                bool high = ArcDistance(xi, eta, h, (second + BetaMax) / 2) <= tol;
                plo = low ? -BetaMax : middle ? first : high ? second : double.PositiveInfinity;
                phi = high ? BetaMax : middle ? second : low ? first : double.NegativeInfinity;
            }
            plo -= BetaMargin; phi += BetaMargin;
            if (plo > lo) lo = plo;
            if (phi < hi) hi = phi;
            if (lo > hi) return false;
        }
        return lo <= hi;
    }

    // numpy.unique(numpy.round(numpy.linspace(1, d - 1, count))) ile aynı dizin kümesi.
    static int Offsets(int d, int count, int[] buffer)
    {
        int size = 0;
        for (int k = 0; k < count; k++)
        {
            double value = count == 1 ? 1.0 : k == count - 1 ? d - 1 : 1.0 + k * ((d - 2.0) / (count - 1));
            int rounded = (int)Math.Round(value, MidpointRounding.ToEven);
            if (size == 0 || buffer[size - 1] != rounded) buffer[size++] = rounded;
        }
        return size;
    }

    public static double Run(string input, string output)
    {
        int m, depth, probe, refine, fullBelow;
        double tolerance;
        double[] pts;
        byte[] straight;
        using (var reader = new BinaryReader(File.OpenRead(input)))
        {
            m = reader.ReadInt32(); depth = reader.ReadInt32(); probe = reader.ReadInt32();
            refine = reader.ReadInt32(); fullBelow = reader.ReadInt32();
            tolerance = reader.ReadDouble();
            pts = new double[2 * m];
            for (int k = 0; k < 2 * m; k++) pts[k] = reader.ReadDouble();
            straight = reader.ReadBytes((depth + 1) * m);
        }
        double tol = tolerance + Margin;
        var valid = new byte[depth * m];
        var offsets = new int[Math.Max(depth, 1)];
        var watch = Stopwatch.StartNew();
        for (int d = 2; d <= depth; d++)
        {
            int count = Offsets(d, Math.Min(d - 1, probe), offsets);
            bool any = false;
            for (int i = 0; i < m; i++)
            {
                if (straight[d * m + i] != 0) continue;
                if (Feasible(pts, m, i, d, offsets, count, tol)) { valid[(d - 1) * m + i] = 1; any = true; }
            }
            if (!any) continue;
            int first = -1, second = -1;
            if (d <= fullBelow) { first = d - 1; if (refine > probe && d - 1 > 2 * refine) { first = refine; second = d - 1; } }
            else if (refine > probe) first = refine;
            foreach (int stage in new[] { first, second })
            {
                if (stage < 0 || stage <= count) continue;
                count = Offsets(d, Math.Min(d - 1, stage), offsets);
                for (int i = 0; i < m; i++)
                    if (valid[(d - 1) * m + i] != 0 && !Feasible(pts, m, i, d, offsets, count, tol))
                        valid[(d - 1) * m + i] = 0;
            }
        }
        watch.Stop();
        File.WriteAllBytes(output, valid);
        return watch.Elapsed.TotalSeconds;
    }
}
