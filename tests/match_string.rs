fn main() {
    let lang = "rust";
    let rating = match lang {
        "rust" => "great",
        "python" => "good",
        _ => "ok",
    };
    println!("{}", rating);
}
