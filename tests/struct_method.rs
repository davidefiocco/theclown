struct Rect {
    w: f64,
    h: f64,
}

impl Rect {
    fn new(w: f64, h: f64) -> Rect {
        Rect { w: w, h: h }
    }

    fn area(&self) -> f64 {
        self.w * self.h
    }

    fn perimeter(&self) -> f64 {
        2.0 * (self.w + self.h)
    }
}

fn main() {
    let r = Rect::new(3.0, 4.0);
    println!("{}", r.area());
    println!("{}", r.perimeter());
}
