<?php
// demo/inject.php — build.sh çağırır. Render edilmiş statik HTML'e demo'yu enjekte eder:
//   1) <head>'e canlı ?json=1 fetch'ini yutan shim (Pages'te backend yok)
//   2) </body> öncesine simülasyon motoru <script src="demo.js">
// Not: JS içinde çift tırnak var → PHP tek tırnaklı string kullanılır (kaçış derdi yok).
$f = $argv[1] ?? 'docs/index.html';
$s = file_get_contents($f);

$shim = '<script>(function(){var f=window.fetch;window.fetch=function(u){'
      . 'try{if(typeof u==="string"&&(""+u).indexOf("json=1")>-1)return new Promise(function(){});}catch(e){}'
      . 'return f.apply(this,arguments);};})();</script>';

$s = str_replace('</head>', $shim . "\n</head>", $s);
$s = str_replace('</body>', '<script src="demo.js"></script>' . "\n</body>", $s);

file_put_contents($f, $s);
echo "injected demo into $f\n";
