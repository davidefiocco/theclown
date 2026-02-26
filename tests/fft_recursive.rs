fn fft(re: Vec<f64>, im: Vec<f64>) -> (Vec<f64>, Vec<f64>) {
    let n = re.len();
    if n == 1 {
        return (re, im);
    }
    let mut re_even: Vec<f64> = vec![];
    let mut im_even: Vec<f64> = vec![];
    let mut re_odd: Vec<f64> = vec![];
    let mut im_odd: Vec<f64> = vec![];
    for i in 0..n {
        if i % 2 == 0 {
            re_even.push(re[i]);
            im_even.push(im[i]);
        } else {
            re_odd.push(re[i]);
            im_odd.push(im[i]);
        }
    }
    let (ere, eim) = fft(re_even, im_even);
    let (ore, oim) = fft(re_odd, im_odd);
    let pi: f64 = 3.141592653589793;
    let half = n / 2;
    let mut out_re: Vec<f64> = vec![];
    let mut out_im: Vec<f64> = vec![];
    for _i in 0..n {
        out_re.push(0.0);
        out_im.push(0.0);
    }
    for k in 0..half {
        let ang: f64 = -2.0 * pi * (k as f64) / (n as f64);
        let wr: f64 = ang.cos();
        let wi: f64 = ang.sin();
        let tr: f64 = wr * ore[k] - wi * oim[k];
        let ti: f64 = wr * oim[k] + wi * ore[k];
        out_re[k] = ere[k] + tr;
        out_im[k] = eim[k] + ti;
        out_re[k + half] = ere[k] - tr;
        out_im[k + half] = eim[k] - ti;
    }
    return (out_re, out_im);
}

fn round6(x: f64) -> f64 {
    ((x + 0.0) * 1000000.0).round() / 1000000.0
}

fn main() {
    let n: usize = 256;
    let pulse: usize = 64;
    let mut re: Vec<f64> = vec![];
    let mut im: Vec<f64> = vec![];
    for i in 0..n {
        if i < pulse {
            re.push(1.0);
        } else {
            re.push(0.0);
        }
        im.push(0.0);
    }
    let (out_re, out_im) = fft(re, im);
    for k in 0..n {
        println!("{} {}", round6(out_re[k]), round6(out_im[k]));
    }
}
