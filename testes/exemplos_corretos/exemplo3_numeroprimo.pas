program NumeroPrimo;
var
 num, i: integer;
 primo: boolean;
begin
 writeln('Introduza um numero inteiro positivo:');
 readln(num);
 primo := true;
 i := 2;
 while (i <= (num div 2)) and primo do
 begin
 if (num mod i) = 0 then
 primo := false;
 i := i + 1;
 end;
 if primo then
 writeln(num, ' e um numero primo')
 else
 writeln(num, ' nao e um numero primo')
end.
