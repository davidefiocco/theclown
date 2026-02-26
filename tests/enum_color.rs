enum Color {
    Red,
    Green,
    Blue,
}

fn main() {
    let c = Color::Green;
    match c {
        Color::Red => println!("red"),
        Color::Green => println!("green"),
        Color::Blue => println!("blue"),
    }
}
