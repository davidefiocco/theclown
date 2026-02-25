fn main() {
    let x = { let y = 5; y + 1 };
    println!("{}", y);
}
