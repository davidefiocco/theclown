fn main() {
    let x = 2;
    let result = match x {
        1 | 2 => "small",
        3 | 4 => "medium",
        _ => "large",
    };
    println!("{}", result);
}
